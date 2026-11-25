"""Optimization competitions with a user-reviewed scorer plugin.

profile["data"] for an optimization competition:
    {"kind": "optimization", "scorer": ".kaggle-agent/scorer.py",
     "files": ["data/cities.csv"], "solution_name": "submission.csv"}

scorer.py defines   score(solution_path, data_dir) -> float
and raises an exception for any infeasible or malformed solution. The data
hash covers the data files; the split hash covers the scorer itself, so a
changed scorer is detected and old scores are never mixed with new ones.

Scoring runs in a separate Python process (isolated mode) so a crashing or
slow scorer cannot take down the supervisor.
"""
import json
import math
from pathlib import Path
import subprocess
import sys

from kaggle_agent.execution.gates import require
from kaggle_agent.storage.database import checksum, fingerprint

RUNNER = """
import importlib.util, json, math, sys
spec = importlib.util.spec_from_file_location("competition_scorer", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
value = float(module.score(sys.argv[2], sys.argv[3]))
if not math.isfinite(value):
    raise SystemExit("nonfinite score")
print(json.dumps({"score": value}))
"""


def validate_spec(spec):
    require(isinstance(spec, dict) and spec.get("kind") == "optimization", "Optimization data spec required")
    require(bool(spec.get("scorer")) and bool(spec.get("solution_name")), "Spec needs scorer and solution_name")
    require(Path(spec["solution_name"]).name == spec["solution_name"], "solution_name must be a plain file name")
    require(isinstance(spec.get("files", []), list), "files must be a list")


def identity(root, spec):
    validate_spec(spec)
    root = Path(root)
    files = {name: checksum(root / name) for name in sorted(spec.get("files", []))}
    return dict(data_hash=fingerprint(dict(spec=spec, files=files)), split_hash=checksum(root / spec["scorer"]))


def score_solution(root, spec, solution, *, seconds=600):
    """Exact score of one solution file. Raises if infeasible or the scorer fails."""
    validate_spec(spec)
    root = Path(root).resolve()
    solution = Path(solution).resolve()
    require(solution.is_file(), f"Missing solution file {solution.name}")
    try:
        result = subprocess.run([sys.executable, "-I", "-c", RUNNER, str(root / spec["scorer"]), str(solution), str(root)],
                                capture_output=True, text=True, timeout=seconds, cwd=root)
    except subprocess.TimeoutExpired:
        require(False, "Scorer timed out")
    require(result.returncode == 0, "Infeasible solution or scorer error: " + (result.stderr.strip().splitlines() or ["no detail"])[-1][:300])
    value = json.loads(result.stdout.strip().splitlines()[-1])["score"]
    require(math.isfinite(value), "Nonfinite score")
    return value
