"""Run agent-written scripts under the watchdog and score their outputs.

Contract for a script (see toolkit.py, which handles it for the script):
  - read data paths from the KA_* environment variables;
  - write oof.csv and test.csv (tables) or the solution file (optimization)
    into the directory named by KA_OUT;
  - honor KA_SMOKE=1 (tiny, fast run) and KA_FRACTION (row sample) so the
    smoke and screen stages stay cheap.

The script's folder is copied into the run directory before it runs, so the
code that produced a score is kept byte-for-byte next to its outputs.
"""
import json
import os
from pathlib import Path
import re
import shutil
import sys

from kaggle_agent.execution.gates import require
from kaggle_agent.execution.local import LocalProvider
from kaggle_agent.storage.database import checksum, fingerprint
from kaggle_agent.storage.export_state import atomic_write
from kaggle_agent.supervisor.watchdog import run_process

# Not a sandbox: a same-user script can still do anything you can. These checks
# catch the common, costly mistakes and obvious rule breaks before a run.
FORBIDDEN = [
    (r"competitions\s+submit|competition_submit|\bsubmit_competition\b", "Kaggle submission"),
    (r"\bmodal\s+(run|deploy)\b|import\s+modal\b|from\s+modal\s+import", "Modal (paid compute)"),
    (r"\bvastai\b", "Vast.ai (paid compute)"),
    (r"\.kaggle-agent[/\\\\](?!workspace)", "supervisor files (ledger, evaluator state, folds)"),
    (r"global\.sqlite3", "supervisor database"),
    (r"ANTHROPIC_API_KEY|OPENAI_API_KEY|KAGGLE_KEY", "credentials"),
]
CODE_SUFFIXES = {".py", ".json", ".yaml", ".yml", ".txt", ".md"}


def check_scripts(folder, entry):
    folder = Path(folder)
    require((folder / entry).is_file(), f"Missing entry script {entry}")
    problems = []
    for path in sorted(folder.rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern, label in FORBIDDEN:
            if re.search(pattern, text):
                problems.append(f"{path.name}: uses {label}")
    require(not problems, "Script blocked: " + "; ".join(problems))


def code_hash(folder):
    """Fingerprint of the code files in a workspace (outputs and data ignored)."""
    folder = Path(folder)
    files = {str(p.relative_to(folder)).replace("\\", "/"): checksum(p)
             for p in sorted(folder.rglob("*")) if p.is_file() and p.suffix in CODE_SUFFIXES
             and "__pycache__" not in p.parts}
    require(bool(files), "Workspace has no code files")
    return fingerprint(files)


def copy_code(source, target):
    shutil.copytree(source, target, ignore=lambda d, names: [n for n in names if n == "__pycache__"
                    or (Path(d, n).is_file() and Path(n).suffix not in CODE_SUFFIXES)])


class ScriptProvider(LocalProvider):
    """Same durable intent/status files as LocalProvider; runs a script instead."""
    name = "script"

    def launch(self, key, payload):
        root = self.directory / key
        require(not root.exists(), "Existing launch intent; reconcile rather than relaunch")
        root.mkdir(parents=True)
        atomic_write(root / "plan.json", json.dumps(payload, allow_nan=False))
        state = dict(state="INTENT", job_id=key)
        atomic_write(root / "status.json", json.dumps(state))
        copy_code(payload["workspace"], root / "code")
        require(code_hash(root / "code") == payload["config"]["script_sha256"], "Workspace changed during launch")

        def heartbeat(**process):
            state.update(state="RUNNING", **process)
            atomic_write(root / "status.json", json.dumps(state))
            self.heartbeat(**process)

        env = os.environ.copy()
        for name in list(env):
            if name.endswith("API_KEY") or name in {"KAGGLE_KEY", "KAGGLE_USERNAME"}:
                env.pop(name)
        threads = str(self.threads)
        env.update(OMP_NUM_THREADS=threads, OPENBLAS_NUM_THREADS=threads, MKL_NUM_THREADS=threads,
                   NUMEXPR_NUM_THREADS=threads, KAGGLE_AGENT_THREADS=threads)
        env.update({k: str(v) for k, v in payload["env"].items()})
        env["KA_OUT"] = str(root)
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2]) + os.pathsep + env.get("PYTHONPATH", "")
        outcome = run_process([sys.executable, payload["entry"]], root / "code", root / "worker.log",
                              seconds=self.seconds, memory_mb=self.memory_mb, heartbeat=heartbeat,
                              should_stop=self.should_stop, env=env)
        ok = outcome["exit_code"] == 0 and outcome["termination_reason"] == "exit"
        if ok:
            try:
                self.write_result(root, payload)
            except Exception as error:  # scoring failure = failed run, reason kept
                ok = False
                outcome["scoring_error"] = str(error)[:500]
        state.update(state="COMPLETED" if ok else "STOPPED" if outcome["termination_reason"] == "user_stop" else "FAILED",
                     outcome=outcome)
        atomic_write(root / "status.json", json.dumps(state))
        return key

    def write_result(self, root, payload):
        from kaggle_agent.data import score as score_tables
        from kaggle_agent.pipelines.plugin import score_solution
        spec, data_root = payload["data_spec"], payload["data_root"]
        if spec["kind"] == "optimization":
            names = [spec["solution_name"]]
            scores = [score_solution(data_root, spec, root / spec["solution_name"])]
            score_type = "exact"
        else:
            names = ["oof.csv", "test.csv"]
            fidelity = payload["config"].get("_fidelity", "full")
            scores = score_tables(data_root, spec, payload["task"], payload["metric"], root,
                                  subset=fidelity != "full", min_fraction=0.0)
            score_type = "base_oof"
        result = dict(complete=True, evaluator_hash=payload["evaluator_hash"], config_hash=fingerprint(payload["config"]),
                      data_hash=payload["data_hash"], split_hash=payload["split_hash"], fold_scores=scores,
                      score_type=score_type, artifacts={name: checksum(root / name) for name in names})
        notes = root / "notes.json"
        if notes.is_file():
            try:
                result["script_notes"] = json.loads(notes.read_text(encoding="utf-8"))
            except ValueError:
                pass
        atomic_write(root / "result.json", json.dumps(result, allow_nan=False))


def tail(path, lines=60):
    path = Path(path)
    if not path.is_file():
        return ""
    return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])
