"""Helpers for agent-written experiment scripts.

    from kaggle_agent import toolkit as kt
    d = kt.load()                       # train/test DataFrames, frozen folds, settings
    for fold, tr, va in kt.splits(d):   # fixed folds; time scheme handled
        ...
    kt.save(d, oof, test_pred)          # writes oof.csv/test.csv where the supervisor expects

Works in three places: under the supervisor (KA_* variables set), with
`python -m kaggle_agent register-run` afterwards, or on any machine where the
script finds the same files. Smoke and screen stages are handled by load():
it samples rows when KA_SMOKE or KA_FRACTION is set.
"""
import json
import os
from pathlib import Path


def _env(name, default=None):
    value = os.environ.get(name, default)
    if value is None:
        raise RuntimeError(f"{name} is not set; run through the supervisor or set it yourself")
    return value


def settings():
    return dict(
        smoke=os.environ.get("KA_SMOKE") == "1",
        fraction=float(os.environ.get("KA_FRACTION", "1")),
        seed=int(os.environ.get("KA_SEED", "42")),
        threads=int(os.environ.get("KAGGLE_AGENT_THREADS", "1")),
        out=Path(os.environ.get("KA_OUT", ".")),
        best=os.environ.get("KA_BEST") or None,
    )


def load():
    """Train/test tables aligned with the frozen folds, sampled for smoke/screen.

    Returns a dict: train, test (DataFrames), folds (numpy array aligned with
    train rows), id, target, task, metric, classes, scheme, plus settings().
    Classification targets are encoded 0..K-1 in d["y"] in the class order the
    evaluator uses; write probabilities in that column order.
    """
    import numpy as np
    from kaggle_agent import data as tables
    spec = json.loads(_env("KA_DATA_SPEC"))
    root = Path(_env("KA_DATA_ROOT"))
    task, metric = _env("KA_TASK"), _env("KA_METRIC")
    s = settings()
    train = tables.read_table(tables.resolve(root, spec, "train"))
    test = tables.read_table(tables.resolve(root, spec, "test"))
    folds_table = tables.read_table(tables.resolve(root, spec, "folds"))
    fold_map = dict(zip(folds_table["id"].astype(str), folds_table["fold"].astype(int)))
    folds = np.array([fold_map[str(i)] for i in train[spec["id_column"]]])
    if s["smoke"] or s["fraction"] < 1:
        rng = np.random.default_rng(s["seed"])
        keep = np.zeros(len(train), dtype=bool)
        for fold in np.unique(folds):
            rows = np.flatnonzero(folds == fold)
            n = max(2, int(len(rows) * s["fraction"]))
            if s["smoke"]:
                n = min(n, max(2, int(os.environ.get("KA_SMOKE_ROWS", "2000")) // max(1, len(np.unique(folds)))))
            keep[rng.choice(rows, size=min(n, len(rows)), replace=False)] = True
        train, folds = train.loc[keep].reset_index(drop=True), folds[keep]
    classes = tables.class_order(root, spec) if task == "classification" else None
    y = train[spec["target_column"]]
    if classes is not None:
        y = y.map({c: i for i, c in enumerate(classes)})
    return dict(train=train, test=test, folds=folds, y=y.to_numpy(), id=spec["id_column"],
                target=spec["target_column"], task=task, metric=metric, classes=classes,
                scheme="time" if (folds == -1).any() else spec.get("fold_scheme", "kfold"), **s)


def features(d):
    """Default feature columns: everything except id and target."""
    return [c for c in d["train"].columns if c not in {d["id"], d["target"]}]


def splits(d):
    """Yield (fold, train_index, valid_index). Time scheme trains on earlier blocks only."""
    import numpy as np
    folds = d["folds"]
    for fold in sorted(set(folds.tolist()) - {-1}):
        train = np.flatnonzero(folds < fold) if d["scheme"] == "time" else np.flatnonzero(folds != fold)
        yield fold, train, np.flatnonzero(folds == fold)


def score(d, y_true, prediction):
    """Local metric, same code as the independent evaluator (for printing only)."""
    from kaggle_agent.evaluation.validation import metric_score
    import numpy as np
    p = np.asarray(prediction, dtype=float)
    if d["task"] == "classification" and p.ndim == 1:
        p = np.column_stack([1 - p, p])
    return metric_score(d["metric"], list(y_true), p.tolist())


def save(d, oof, test_prediction, notes=None):
    """Write oof.csv (scored rows only) and test.csv into KA_OUT.

    oof: array aligned with d["train"] rows (rows in fold -1 are dropped here).
    For classification pass (n, K) probabilities, or (n,) for the positive class.
    notes: optional dict saved as notes.json (what changed, why) for the log.
    """
    import numpy as np
    from kaggle_agent import data as tables
    oof, test_prediction = np.asarray(oof, dtype=float), np.asarray(test_prediction, dtype=float)
    scored = d["folds"] != -1
    ids = d["train"][d["id"]].astype(str).to_numpy()
    tables.write_predictions(d["out"] / "oof.csv", ids[scored], oof[scored])
    tables.write_predictions(d["out"] / "test.csv", d["test"][d["id"]].astype(str).tolist(), test_prediction)
    if notes:
        (d["out"] / "notes.json").write_text(json.dumps(notes, indent=2, default=str), encoding="utf-8")


def tune(space, objective, *, max_trials=20, seconds=600, direction="minimize", seed=42):
    """Bounded Optuna search (falls back to grid order if Optuna is missing)."""
    from kaggle_agent.execution.efficiency import optuna_search, bounded_search
    try:
        return optuna_search(space, objective, max_trials=max_trials, seconds=seconds, seed=seed, direction=direction)
    except ImportError:
        best = bounded_search(space, objective, max_trials=max_trials, seconds=seconds, direction=direction)[0]
        return dict(parameters=best["config"], score=best["score"], trials=max_trials)


def optimization():
    """Settings for optimization solvers: data dir, output path, current best solution."""
    spec = json.loads(_env("KA_DATA_SPEC"))
    s = settings()
    return dict(data_dir=Path(_env("KA_DATA_ROOT")), files=spec.get("files", []),
                solution=s["out"] / spec["solution_name"], **s)
