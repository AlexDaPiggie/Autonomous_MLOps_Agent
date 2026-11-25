"""The referee: register any run's outputs, score them independently, promote champions.

Used by `python -m kaggle_agent register-run` (manual work, Modal jobs, any
script) and by the code-writing loop. Every registered run gets a copy of its
code and outputs under .kaggle-agent/runs/<id>/, a fingerprint, independently
recomputed fold scores, and a champion check against the current best.
"""
import json
from pathlib import Path
import shutil
import uuid

from kaggle_agent.execution.gates import require
from kaggle_agent.storage.database import checksum, fingerprint
from kaggle_agent.storage.export_state import atomic_write


def is_real(profile):
    return isinstance(profile.get("data"), dict) and profile["data"].get("kind") in {"tables", "optimization"}


def identity(directory, profile):
    spec = profile["data"]
    if spec["kind"] == "optimization":
        from kaggle_agent.pipelines.plugin import identity as plugin_identity
        return plugin_identity(directory, spec)
    from kaggle_agent import data as tables
    return tables.identity(directory, spec)


def metadata(directory, profile, config, *, hypothesis, seed=None):
    from kaggle_agent.evaluation.validation import evaluator_version
    from kaggle_agent.execution.identity import code_version
    current = identity(directory, profile)
    require(current == {k: profile[k] for k in ("data_hash", "split_hash")},
            "Data, folds or scorer changed since the profile was frozen; re-init or review explicitly")
    return dict(code_hash=code_version(), config=config, seed=config.get("seed", 42) if seed is None else seed,
                metric=profile["metric"], evaluator_hash=evaluator_version(), data_spec=profile["data"],
                data_root=str(Path(directory).resolve()), task=profile["task"], hypothesis=hypothesis, **current)


def register(store, controller, directory, profile, *, oof=None, test=None, solution=None, code=(), config=None,
             fidelity="full", hypothesis="manual run", branch=None, parent=None, seed=None, source="manual"):
    """Copy outputs + code into the run folder, record, score, try to promote."""
    from kaggle_agent.execution.script import code_hash
    require(is_real(profile), "register-run needs a real data profile (tables or optimization)")
    directory = Path(directory).resolve()
    key = uuid.uuid4().hex
    root = directory / ".kaggle-agent" / "runs" / key
    root.mkdir(parents=True)
    spec = profile["data"]
    if spec["kind"] == "optimization":
        require(solution is not None, "Optimization runs need --solution")
        shutil.copyfile(solution, root / spec["solution_name"])
        names = [spec["solution_name"]]
        score_type = "exact"
    else:
        require(oof is not None and test is not None, "Table runs need --oof and --test")
        shutil.copyfile(oof, root / "oof.csv")
        shutil.copyfile(test, root / "test.csv")
        names = ["oof.csv", "test.csv"]
        score_type = "base_oof"
    code_dir = root / "code"
    code_dir.mkdir()
    for path in code:
        path = Path(path)
        require(path.is_file(), f"Missing code file {path}")
        shutil.copyfile(path, code_dir / path.name)
    if not any(code_dir.iterdir()):
        (code_dir / "UNKNOWN_CODE.txt").write_text("No code files were given to register-run.\n", encoding="utf-8")
    config = dict(config or {}) | dict(script_sha256=code_hash(code_dir), _fidelity=fidelity)
    meta = metadata(directory, profile, config, hypothesis=hypothesis, seed=seed)
    result = dict(complete=True, score_type=score_type, artifacts={n: checksum(root / n) for n in names})
    controller.acquire()
    try:
        key, result = controller.record(meta, result, root, fidelity=fidelity, branch=branch, parent=parent, source=source)
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise
    finally:
        controller.release()
    summary = dict(experiment=key, fidelity=fidelity, fold_scores=result["fold_scores"],
                   mean=sum(result["fold_scores"]) / len(result["fold_scores"]))
    if fidelity == "full":
        summary["promotion"] = promote_and_vault(store, controller.competition, key, directory, profile)
    return summary


def promote_and_vault(store, competition, key, directory, profile, *, ensemble=False):
    """Champion check; for optimization keep the best solution file safe."""
    from kaggle_agent.evaluation.validation import promote
    result = promote(store, competition, key, ensemble=ensemble)
    if result.get("improved") and profile["data"]["kind"] == "optimization":
        spec = profile["data"]
        source = Path(store.rows("SELECT path FROM predictions WHERE experiment=?", (key,))[0]["path"])
        best = Path(directory) / ".kaggle-agent" / "best"
        best.mkdir(parents=True, exist_ok=True)
        temp = best / (spec["solution_name"] + ".tmp")
        shutil.copyfile(source, temp)
        temp.replace(best / spec["solution_name"])
        atomic_write(best / "best.json", json.dumps(dict(experiment=key, sha256=checksum(source)), indent=2))
    return result


def best_solution(directory, profile):
    if profile.get("data", {}).get("kind") != "optimization":
        return None
    path = Path(directory) / ".kaggle-agent" / "best" / profile["data"]["solution_name"]
    return path if path.is_file() else None


def leaderboard(store, competition, direction, limit=10):
    """Completed full runs, best first: what the agent sees before its next idea."""
    rows = store.rows("SELECT id,fidelity,metadata,result,created FROM experiments WHERE competition=? AND state='COMPLETED' AND fidelity='full' ORDER BY created", (competition,))
    entries = []
    for row in rows:
        result, meta = json.loads(row["result"]), json.loads(row["metadata"])
        scores = result["fold_scores"]
        entries.append(dict(experiment=row["id"], mean=sum(scores) / len(scores), folds=len(scores),
                            score_type=result.get("score_type"), hypothesis=meta.get("hypothesis", ""),
                            notes=result.get("script_notes"), created=row["created"]))
    entries.sort(key=lambda e: e["mean"], reverse=direction == "maximize")
    return entries[:limit]


def assess_ensemble(store, controller, directory, profile, *, max_sources=5):
    """Blend the best registered full runs; promote only if the blend beats its own
    single-model baseline on held-out meta folds AND the current ensemble champion."""
    from kaggle_agent import data as tables
    from kaggle_agent.evaluation.assessment import assess_tables
    from kaggle_agent.evaluation.validation import direction
    if profile["data"]["kind"] != "tables":
        return None
    way = direction(profile["metric"])
    board = [e for e in leaderboard(store, controller.competition, way, limit=50) if e["score_type"] == "base_oof"]
    picked = board[:max_sources]
    if len(picked) < 2:
        return None
    sources = []
    for entry in picked:
        row = store.rows("SELECT path,checksum FROM predictions WHERE experiment=? AND path LIKE ?", (entry["experiment"], "%oof.csv"))[0]
        sources.append(dict(path=row["path"], sha256=row["checksum"], experiment=entry["experiment"]))
    config = dict(seed=42, metric=profile["metric"], blend_sources=[dict(path=s["path"], sha256=s["sha256"]) for s in sources], _fidelity="full")
    meta = metadata(directory, profile, config, hypothesis="Blend of top registered runs (stacker vs hill climbing, meta-CV)")
    from kaggle_agent.execution.gates import experiment_fingerprint
    if store.rows("SELECT id FROM experiments WHERE competition=? AND fingerprint=?", (controller.competition, experiment_fingerprint(meta))):
        return None
    blend = assess_tables(directory, profile["data"], profile["task"], config["blend_sources"], profile["metric"])
    key = uuid.uuid4().hex
    root = Path(directory) / ".kaggle-agent" / "runs" / key
    root.mkdir(parents=True)
    tables.write_predictions(root / "oof.csv", blend["scored_ids"], blend["oof"])
    tables.write_predictions(root / "test.csv", tables.test_ids(directory, profile["data"]), blend["test"])
    result = dict(complete=True, score_type="conditional_meta_cv", ensemble_baseline_scores=blend["ensemble_baseline_scores"],
                  combiner=blend["combiner"], combiner_candidates=blend["candidates"], weights=blend["weights"],
                  sources=[s["experiment"] for s in sources],
                  artifacts={n: checksum(root / n) for n in ("oof.csv", "test.csv")})
    try:  # caller holds the supervisor lease
        key, result = controller.record(meta, result, root, fidelity="full", source="ensemble")
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise
    promotion = promote_and_vault(store, controller.competition, key, directory, profile, ensemble=True)
    return dict(experiment=key, combiner=result["combiner"], fold_scores=result["fold_scores"], promotion=promotion)
