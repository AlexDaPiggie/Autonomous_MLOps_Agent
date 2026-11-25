"""Kaggle submissions: build the file from a champion, check it, respect the daily
quota, send it with the official CLI and log it. Used by `ka submit` (manual)
and by `ka go` when auto-submit is on. Decisions never use the public score.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import uuid

from kaggle_agent.execution.gates import require
from kaggle_agent.storage.database import checksum, utcnow

SCHEMA = """CREATE TABLE IF NOT EXISTS submissions(
 id TEXT PRIMARY KEY, competition TEXT NOT NULL, experiment TEXT, file TEXT NOT NULL, sha256 TEXT NOT NULL,
 message TEXT NOT NULL, created TEXT NOT NULL, status TEXT NOT NULL, public_score REAL,
 auto INTEGER NOT NULL DEFAULT 0, cv REAL, error TEXT)"""


def ensure(store):
    with store.transaction() as db:
        db.execute(SCHEMA)


DEFAULTS = dict(auto=False, daily_limit=5, reserve=1, slug=None, sample=None)


def settings(directory):
    """Submission settings live in .kaggle-agent/submission.json (not in the frozen
    profile), so turning auto-submit on or off never changes the competition identity."""
    path = Path(directory) / ".kaggle-agent" / "submission.json"
    return DEFAULTS | (json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {})


def save_settings(directory, **changes):
    from kaggle_agent.storage.export_state import atomic_write
    value = settings(directory) | changes
    atomic_write(Path(directory) / ".kaggle-agent" / "submission.json", json.dumps(value, indent=2))
    return value


def mean_cv(store, experiment):
    row = store.rows("SELECT result FROM experiments WHERE id=?", (experiment,))
    return statistics.mean(json.loads(row[0]["result"])["fold_scores"]) if row and row[0]["result"] else None


def best_experiment(store, competition, profile):
    """The better of the standalone and ensemble champions by mean CV."""
    comp = store.rows("SELECT champion,ensemble_champion FROM competitions WHERE id=?", (competition,))[0]
    options = [e for e in (comp["champion"], comp["ensemble_champion"]) if e]
    if not options:
        return None
    sign = 1 if profile.get("direction", "minimize") == "maximize" else -1
    return max(options, key=lambda e: sign * mean_cv(store, e))


def run_dir(store, experiment):
    rows = store.rows("SELECT path FROM predictions WHERE experiment=?", (experiment,))
    require(bool(rows), "That run has no registered outputs")
    return Path(rows[0]["path"]).parent


def build(store, competition, directory, profile, experiment):
    """Write .kaggle-agent/submissions/<run>.csv in the sample_submission format."""
    import numpy as np
    import pandas as pd
    from kaggle_agent import data as tables
    directory = Path(directory)
    spec, sub = profile["data"], settings(directory)
    out = directory / ".kaggle-agent" / "submissions"
    out.mkdir(parents=True, exist_ok=True)
    source = run_dir(store, experiment)
    if spec["kind"] == "optimization":
        solution = source / spec["solution_name"]
        require(solution.is_file(), "Run has no solution file")
        target = out / f"{experiment[:12]}-{spec['solution_name']}"
        target.write_bytes(solution.read_bytes())
        return target
    require(bool(sub["sample"]) and (directory / sub["sample"]).is_file(), "No sample_submission file set for this competition")
    sample = tables.read_table(directory / sub["sample"])
    id_col, value_cols = sample.columns[0], list(sample.columns[1:])
    require(bool(value_cols), "sample_submission has no value column")
    classes = spec.get("classes")
    n_classes = len(classes) if profile["task"] == "classification" else None
    ids, pred = tables.read_predictions(source / "test.csv", n_classes=n_classes)
    by_id = dict(zip(ids, range(len(ids))))
    sample_ids = sample[id_col].astype(str).tolist()
    require(set(sample_ids) == set(ids) and len(sample_ids) == len(ids), "Run's test IDs differ from sample_submission IDs")
    pred = np.asarray(pred)[[by_id[i] for i in sample_ids]]
    frame = pd.DataFrame({id_col: sample[id_col]})
    if profile["task"] != "classification":
        require(len(value_cols) == 1, "Regression submission expects one value column")
        frame[value_cols[0]] = pred
    elif len(value_cols) > 1:
        names = [str(c) for c in classes]
        require(sorted(map(str, value_cols)) == sorted(names), "Per-class columns do not match the class list")
        for col in value_cols:
            frame[col] = pred[:, names.index(str(col))]
    elif profile["metric"] == "map3":
        top = np.argsort(-pred, axis=1, kind="stable")[:, :3]
        frame[value_cols[0]] = [" ".join(str(classes[k]) for k in row) for row in top]
    else:
        column = sample[value_cols[0]]
        probabilities = (pd.api.types.is_float_dtype(column) and not np.allclose(column.dropna() % 1, 0)) or \
                        (profile["metric"] in {"roc_auc", "log_loss"} and n_classes == 2)
        if probabilities and n_classes == 2:
            frame[value_cols[0]] = pred[:, 1]
        else:
            frame[value_cols[0]] = [classes[k] for k in pred.argmax(axis=1)]
    check(frame, sample)
    target = out / f"{experiment[:12]}.csv"
    frame.to_csv(target, index=False)
    return target


def check(frame, sample):
    import numpy as np
    require(list(frame.columns) == list(sample.columns), "Columns differ from sample_submission")
    require(len(frame) == len(sample), "Row count differs from sample_submission")
    require(frame[frame.columns[0]].astype(str).is_unique, "Duplicate IDs")
    for col in frame.columns[1:]:
        require(not frame[col].isna().any(), f"Missing values in {col}")
        from pandas.api.types import is_numeric_dtype
        if is_numeric_dtype(frame[col]):
            require(bool(np.isfinite(frame[col].to_numpy(dtype=float)).all()), f"Non-finite values in {col}")


def quota(store, competition, directory):
    ensure(store)
    sub = settings(directory)
    today = datetime.now(timezone.utc).date().isoformat()
    used = store.rows("SELECT count(*) AS n FROM submissions WHERE competition=? AND substr(created,1,10)=? AND status!='failed'",
                      (competition, today))[0]["n"]
    return dict(used_today=used, limit=sub["daily_limit"], reserve=sub["reserve"],
                manual_left=max(0, sub["daily_limit"] - used), auto_left=max(0, sub["daily_limit"] - sub["reserve"] - used))


def last_submitted(store, competition):
    ensure(store)
    rows = store.rows("SELECT experiment FROM submissions WHERE competition=? AND status!='failed' ORDER BY created DESC LIMIT 1", (competition,))
    return rows[0]["experiment"] if rows else None


def submit(store, competition, directory, profile, experiment=None, *, auto=False, confirm=None):
    """Build, check and send. Returns a dict describing what happened."""
    from kaggle_agent import kaggle_cli
    ensure(store)
    sub = settings(directory)
    require(bool(sub["slug"]), "This competition has no Kaggle slug; set up with `ka new <url>`")
    experiment = experiment or best_experiment(store, competition, profile)
    require(experiment is not None, "No champion yet")
    rows = store.rows("SELECT state,fidelity FROM experiments WHERE id=? AND competition=?", (experiment, competition))
    require(bool(rows) and rows[0]["state"] == "COMPLETED" and rows[0]["fidelity"] == "full", "Only completed full runs can be submitted")
    left = quota(store, competition, directory)
    require((left["auto_left"] if auto else left["manual_left"]) > 0,
            "Daily submission limit reached" + (" (one slot kept for you)" if auto else ""))
    path = build(store, competition, directory, profile, experiment)
    cv = mean_cv(store, experiment)
    message = f"ka {experiment[:8]} cv={cv:.6g} {'auto' if auto else 'manual'}"
    if confirm is not None and not confirm(path, cv, left):
        return dict(sent=False, reason="cancelled", file=str(path))
    key = uuid.uuid4().hex
    try:
        kaggle_cli.submit(sub["slug"], path, message)
        status, error = "submitted", None
    except Exception as exc:  # logged, never retried silently
        status, error = "failed", str(exc)[:400]
    with store.transaction() as db:
        db.execute("INSERT INTO submissions VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                   (key, competition, experiment, str(path), checksum(path), message, utcnow(), status, None, int(auto), cv, error))
        store.event("submission", dict(experiment=experiment, status=status, auto=auto, error=error), competition, db)
    return dict(sent=status == "submitted", status=status, error=error, experiment=experiment, cv=cv, file=str(path), message=message)


def maybe_auto(store, competition, directory, profile):
    """Auto mode: send the best champion once, if it is new and quota allows."""
    sub = settings(directory)
    if not sub["auto"] or not sub["slug"]:
        return None
    best = best_experiment(store, competition, profile)
    if not best or best == last_submitted(store, competition):
        return None
    if quota(store, competition, directory)["auto_left"] <= 0:
        return dict(sent=False, reason="daily limit (slot kept for you)")
    return submit(store, competition, directory, profile, best, auto=True)


def refresh_scores(store, competition, directory):
    """Fill in public scores from Kaggle (for display only)."""
    from kaggle_agent import kaggle_cli
    ensure(store)
    sub = settings(directory)
    if not sub["slug"]:
        return 0
    pending = store.rows("SELECT id,message FROM submissions WHERE competition=? AND status='submitted' AND public_score IS NULL", (competition,))
    if not pending:
        return 0
    try:
        remote = kaggle_cli.submissions(sub["slug"])
    except Exception:
        return 0
    updated = 0
    with store.transaction() as db:
        for row in pending:
            for item in remote:
                if item.get("description", "").strip() == row["message"]:
                    score = item.get("publicScore") or item.get("public_score")
                    try:
                        value = float(score)
                    except (TypeError, ValueError):
                        continue
                    db.execute("UPDATE submissions SET public_score=?,status='scored' WHERE id=?", (value, row["id"]))
                    updated += 1
                    break
    return updated


def history(store, competition, limit=10):
    ensure(store)
    return store.rows("SELECT * FROM submissions WHERE competition=? ORDER BY created DESC LIMIT ?", (competition, limit))
