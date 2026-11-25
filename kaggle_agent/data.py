"""Real competition tables: CSV/Parquet data specs, frozen folds, ID-based scoring.

A table data spec lives in profile["data"]:
    {"kind": "tables", "train": "data/train.csv", "test": "data/test.csv",
     "id_column": "id", "target_column": "y", "folds": ".kaggle-agent/folds.csv",
     "fold_scheme": "kfold" | "group" | "time", "classes": [...] (classification)}
Paths are relative to the competition directory. folds.csv has columns id,fold.
For the time scheme, fold -1 rows are training-only and are never scored.
"""
import json
from pathlib import Path

from kaggle_agent.execution.gates import require
from kaggle_agent.storage.database import checksum, fingerprint

PREDICTION_FILES = ("oof.csv", "test.csv")


def read_table(path, columns=None):
    import pandas as pd
    path = Path(path)
    require(path.is_file(), f"Missing table {path}")
    if path.suffix.lower() in {".parquet", ".pq"}:
        return pd.read_parquet(path, columns=columns)
    return pd.read_csv(path, usecols=columns)


def resolve(root, spec, key):
    return (Path(root) / spec[key]).resolve()


def validate_spec(spec):
    require(isinstance(spec, dict) and spec.get("kind") == "tables", "Table data spec required")
    for key in ("train", "test", "id_column", "target_column", "folds"):
        require(bool(spec.get(key)), f"Data spec missing {key}")
    require(spec.get("fold_scheme", "kfold") in {"kfold", "group", "time"}, "Unknown fold scheme")


def identity(root, spec):
    """Data hash covers train, test and the spec; split hash covers the fold file."""
    validate_spec(spec)
    data = dict(spec={k: v for k, v in spec.items() if k != "folds"},
                train=checksum(resolve(root, spec, "train")), test=checksum(resolve(root, spec, "test")))
    return dict(data_hash=fingerprint(data), split_hash=checksum(resolve(root, spec, "folds")))


def make_folds_file(root, spec, *, task, n_splits=5, seed=42, group_column=None, time_column=None):
    """Write folds.csv once. Refuses to overwrite: changing folds invalidates history."""
    import numpy as np
    import pandas as pd
    from sklearn.model_selection import GroupKFold, KFold, StratifiedKFold
    target = resolve(root, spec, "folds")
    require(not target.exists(), "Fold file already exists; folds are frozen")
    require(2 <= n_splits <= 20, "Use 2..20 folds")
    columns = [spec["id_column"], spec["target_column"]] + [c for c in (group_column, time_column) if c]
    train = read_table(resolve(root, spec, "train"), columns=columns)
    ids, y = train[spec["id_column"]], train[spec["target_column"]]
    require(ids.is_unique, "Train IDs must be unique")
    folds = np.full(len(train), -1)
    if time_column:
        # Expanding window: blocks 1..k are validation folds, block 0 trains only.
        order = np.argsort(train[time_column].to_numpy(), kind="stable")
        blocks = np.array_split(order, n_splits + 1)
        for fold, rows in enumerate(blocks[1:]):
            folds[rows] = fold
        scheme = "time"
    else:
        if group_column:
            splitter, groups, scheme = GroupKFold(n_splits=n_splits), train[group_column], "group"
        elif task == "classification":
            splitter, groups, scheme = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed), None, "kfold"
        else:
            splitter, groups, scheme = KFold(n_splits=n_splits, shuffle=True, random_state=seed), None, "kfold"
        for fold, (_, valid) in enumerate(splitter.split(np.zeros(len(y)), y, groups)):
            folds[valid] = fold
    target.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"id": ids, "fold": folds}).to_csv(target, index=False)
    return scheme


def class_order(root, spec):
    if spec.get("classes"):
        return list(spec["classes"])
    y = read_table(resolve(root, spec, "train"), columns=[spec["target_column"]])[spec["target_column"]]
    return sorted(y.unique().tolist())


def labels(root, spec, task):
    """IDs, encoded targets and folds, aligned by ID (never by row position)."""
    train = read_table(resolve(root, spec, "train"), columns=[spec["id_column"], spec["target_column"]])
    folds = read_table(resolve(root, spec, "folds"))
    require(list(folds.columns[:2]) == ["id", "fold"], "folds.csv needs columns id,fold")
    ids = train[spec["id_column"]].astype(str)
    require(ids.is_unique, "Train IDs must be unique")
    fold_map = dict(zip(folds["id"].astype(str), folds["fold"].astype(int)))
    require(set(fold_map) == set(ids), "Fold file IDs differ from train IDs")
    y = train[spec["target_column"]]
    if task == "classification":
        classes = class_order(root, spec)
        index = {c: i for i, c in enumerate(classes)}
        require(set(y.unique()) <= set(index), "Train has labels outside the class list")
        y = y.map(index)
    return ids.tolist(), y.tolist(), [fold_map[i] for i in ids]


def test_ids(root, spec):
    test = read_table(resolve(root, spec, "test"), columns=[spec["id_column"]])
    ids = test[spec["id_column"]].astype(str)
    require(ids.is_unique, "Test IDs must be unique")
    return ids.tolist()


def read_predictions(path, *, n_classes=None):
    """Prediction file: column id plus pred (one value) or pred_0..pred_{K-1}."""
    frame = read_table(path)
    require("id" in frame.columns, f"{Path(path).name} needs an id column")
    columns = [c for c in frame.columns if c == "pred" or c.startswith("pred_")]
    require(bool(columns), f"{Path(path).name} needs pred or pred_0.. columns")
    if columns != ["pred"]:
        columns = sorted(columns, key=lambda c: int(c.split("_")[1]))
    values = frame[columns].to_numpy(dtype=float)
    if n_classes is not None:
        if values.shape[1] == 1 and n_classes == 2:
            values = __import__("numpy").column_stack([1 - values[:, 0], values[:, 0]])
        require(values.shape[1] == n_classes, "Prediction columns differ from class count")
    elif values.shape[1] == 1:
        values = values[:, 0]
    return frame["id"].astype(str).tolist(), values


def write_predictions(path, ids, values):
    import numpy as np
    import pandas as pd
    values = np.asarray(values, dtype=float)
    frame = pd.DataFrame({"id": [str(i) for i in ids]})
    if values.ndim == 1:
        frame["pred"] = values
    else:
        for k in range(values.shape[1]):
            frame[f"pred_{k}"] = values[:, k]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def score(root, spec, task, metric, run_dir, *, subset=False, min_fraction=0.0):
    """Independent fold scores from oof.csv/test.csv in run_dir.

    subset=True allows OOF for a sample of rows (screen/smoke stages); full runs
    must cover every scored row. Test predictions must cover every test ID.
    """
    import numpy as np
    from kaggle_agent.evaluation.validation import metric_score, finite
    run_dir = Path(run_dir)
    ids, y, folds = labels(root, spec, task)
    n_classes = len(class_order(root, spec)) if task == "classification" else None
    pred_ids, pred = read_predictions(run_dir / "oof.csv", n_classes=n_classes)
    require(len(set(pred_ids)) == len(pred_ids), "Duplicate OOF IDs")
    require(finite(pred.tolist()), "Nonfinite OOF predictions")
    scored = {i for i, f in zip(ids, folds) if f >= 0}
    given = set(pred_ids)
    require(given <= set(ids), "OOF has IDs that are not in train")
    if subset:
        require(len(given & scored) >= max(1, min_fraction * len(scored)), "Too few OOF rows for this stage")
    else:
        require(scored <= given, "OOF misses scored train rows (no dropping rows)")
    by_id = dict(zip(pred_ids, range(len(pred_ids))))
    fold_scores = []
    for fold in sorted(set(f for f in folds if f >= 0)):
        rows = [k for k, (i, f) in enumerate(zip(ids, folds)) if f == fold and i in given]
        if not rows:
            continue
        p = pred[[by_id[ids[k]] for k in rows]]
        fold_scores.append(metric_score(metric, [y[k] for k in rows], p.tolist()))
    require(len(fold_scores) >= 1, "No scored folds")
    test_pred_ids, test_pred = read_predictions(run_dir / "test.csv", n_classes=n_classes)
    require(sorted(test_pred_ids) == sorted(test_ids(root, spec)), "Test predictions must cover each test ID once")
    require(finite(test_pred.tolist()), "Nonfinite test predictions")
    return fold_scores


def oof_matrix(root, spec, task, run_dir):
    """OOF and test predictions aligned to train/test ID order, for blending."""
    import numpy as np
    n_classes = len(class_order(root, spec)) if task == "classification" else None
    ids, _, _ = labels(root, spec, task)
    pred_ids, pred = read_predictions(Path(run_dir) / "oof.csv", n_classes=n_classes)
    index = dict(zip(pred_ids, range(len(pred_ids))))
    require(set(ids) <= set(index), "Blend inputs need full OOF")
    t_ids = test_ids(root, spec)
    tp_ids, tp = read_predictions(Path(run_dir) / "test.csv", n_classes=n_classes)
    t_index = dict(zip(tp_ids, range(len(tp_ids))))
    return np.asarray(pred)[[index[i] for i in ids]], np.asarray(tp)[[t_index[i] for i in t_ids]]


def describe(root, spec, rows=5):
    """Short column summary for the agent brief (names, dtypes, missing share)."""
    train = read_table(resolve(root, spec, "train"))
    lines = [f"train rows={len(train)} columns={len(train.columns)}"]
    for name in train.columns[:200]:
        column = train[name]
        lines.append(f"- {name}: {column.dtype}, missing={column.isna().mean():.3f}, unique={column.nunique()}")
    return "\n".join(lines)


def save_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2), encoding="utf-8")
