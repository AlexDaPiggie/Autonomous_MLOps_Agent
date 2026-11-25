"""Eight tiny synthetic tasks. No historical ranking or agent-cost claims."""
import json
from pathlib import Path
import time
from kaggle_agent.pipelines.tabular import make_folds,cv_predict
from kaggle_agent.pipelines.optimization import solve_knapsack,check_knapsack
from kaggle_agent.pipelines.forecasting import rolling_origin
from kaggle_agent.evaluation.validation import evaluate,paired_improvement
from kaggle_agent.storage.export_state import atomic_write


def synthetic(task,seed=42):
    import numpy as np
    from sklearn.datasets import make_classification,make_regression
    if task in {"classification","regression"}:
        if task=="classification":X,y=make_classification(n_samples=90,n_features=5,n_informative=3,n_redundant=0,random_state=seed)
        else:X,y=make_regression(n_samples=90,n_features=5,n_informative=4,noise=3,random_state=seed)
        folds=make_folds(y,task=task,n_splits=3,seed=seed)
        return dict(task=task,ids=[f"row-{i}" for i in range(90)],X=X.tolist(),y=y.tolist(),folds=folds,test_ids=[f"test-{i}" for i in range(4)],test_X=X[:4].tolist())
    if task=="optimization":
        rng=np.random.default_rng(seed)
        return dict(task=task,weights=rng.integers(1,15,20).tolist(),values=rng.integers(1,30,20).tolist(),capacity=50)
    return dict(task=task,values=[float(i*.1+np.sin(i*2*np.pi/6)) for i in range(60)],times=list(range(60)),origins=[36,42,48],horizon=6,season=6)


def run_dataset(data,config):
    task=data["task"];seed=config.get("seed",42)
    if config.get("blend_sources"):
        from kaggle_agent.evaluation.assessment import assess
        return assess(data,config["blend_sources"],config["metric"],config.get("baseline_index",0))
    if task in {"classification","regression"}:
        if "groups" in data:
            from kaggle_agent.pipelines.tabular import validate_group_folds
            validate_group_folds(data["groups"],data["folds"])
        prediction=cv_predict(data["X"],data["y"],data["folds"],data["test_X"],task=task,
                              family=config.get("family","linear"),seed=seed,categorical=data.get("categorical",()),
                              parameters=config.get("parameters"),seeds=config.get("seeds",1),
                              full_refit=config.get("full_refit",False),**config.get("options",{}))
        result=evaluate(data["ids"],data["y"],data["folds"],data["ids"],prediction["oof"],config["metric"])
        return dict(ids=data["ids"],predictions=prediction["oof"],test_ids=data["test_ids"],test_predictions=prediction["test"],fold_scores=result["fold_scores"],score_type="base_oof")
    if task=="optimization":
        result=solve_knapsack(data["weights"],data["values"],data["capacity"],seed=seed,
                              iterations=config.get("iterations",100),operator=config.get("operator","anneal"))
        return result|dict(fold_scores=[result["score"]],score_type="exact")
    return rolling_origin(data["values"],data["times"],data["origins"],data["horizon"],season=data["season"],
                          family=config.get("family","seasonal_naive"),metric=config["metric"])


def benchmark(output,seeds=(11,29)):
    from kaggle_agent.execution.local import LocalProvider
    from kaggle_agent.storage.database import checksum,fingerprint
    from kaggle_agent.evaluation.validation import evaluator_version
    import uuid
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    provider=LocalProvider(output/"jobs",seconds=60,memory_mb=1024)
    rows=[]
    for task in ("classification","regression","optimization","forecasting"):
        for seed in seeds:
            data=synthetic(task,seed)
            dataset=output/f"{task}-{seed}.json"
            atomic_write(dataset,json.dumps(data))
            for variant in ("original_baseline","upgraded"):
                # A reproducible baseline proxy; the original repo had no executable
                # agent runner. This is NOT a measurement of original agent behavior.
                baseline_config=dict(seed=seed,metric="log_loss" if task=="classification" else "rmse")
                if task=="optimization":baseline_config["operator"]="greedy"
                config=baseline_config.copy()
                if task=="optimization":config["operator"]="greedy" if variant=="original_baseline" else "anneal"
                elif task=="forecasting":config["family"]="seasonal_naive" if variant=="original_baseline" else "lag_ridge"
                elif variant=="upgraded":config["family"]="forest"
                start=time.monotonic()
                key=uuid.uuid4().hex
                provider.launch(key,dict(dataset=str(dataset),config=config,benchmark_configs=[baseline_config,config],
                                         evaluator_hash=evaluator_version(),data_hash=checksum(dataset),split_hash=fingerprint(data.get("folds",data.get("origins",[])))))
                state=provider.reconcile(key)
                if state["state"]!="COMPLETED":raise RuntimeError(f"Synthetic benchmark {task}/{seed}/{variant} failed; inspect {provider.directory/key}")
                baseline,result=json.loads((provider.directory/key/"benchmark-pair.json").read_text())
                comparison=paired_improvement(result["fold_scores"],baseline["fold_scores"],"maximize" if task=="optimization" else "minimize")
                selected=result if comparison["improved"] else baseline
                rows.append(dict(task=task,seed=seed,variant=variant,seconds=time.monotonic()-start,
                                 fold_scores=selected["fold_scores"],baseline_scores=baseline["fold_scores"],
                                 challenger_scores=result["fold_scores"],challenger_accepted=comparison["improved"],
                                 complete=True,cost_cents=0,tokens=None,interventions=0,config=config,
                                 matched_trials=2,runtime_cap_seconds=60))
    report=dict(kind="synthetic_pipeline_comparison",tasks=8,runs=len(rows),rows=rows,
                limitations=["Original agent runner absent: baseline is a proxy, not measured original agent performance",
                             "No paid inference or cloud jobs; token metrics unavailable",
                             "Synthetic tasks do not establish medal or private leaderboard performance",
                             "Two candidate trials per variant/task/seed with identical runtime caps; wall times measured, not artificially equalized",
                             "Champion selection reuses CV folds; this comparison measures retention behavior, not unbiased generalization after search"])
    atomic_write(Path(output)/"benchmark.json",json.dumps(report,indent=2))
    return report


# ---------------------------------------------------------------------------
# End-to-end benchmark on a realistic-shape synthetic competition (CSV tables).
# Compares the two automatic modes under the same data, folds, evaluator and
# limits. The "code" mode uses a scripted mock coder (hand-written scripts in a
# fixed order), so this measures what each mode is ABLE to express, not how
# good a real LLM is. No inference, no network, no money.
# ---------------------------------------------------------------------------

BENCH_SCRIPTS = [
    ("Baseline: logistic regression on numeric columns", '''
import numpy as np
from pandas.api.types import is_numeric_dtype
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from kaggle_agent import toolkit as kt
d = kt.load()
cols = [c for c in kt.features(d) if is_numeric_dtype(d["train"][c])]
X, T, y = d["train"][cols].to_numpy(), d["test"][cols].to_numpy(), d["y"]
oof, test = np.zeros((len(y), 2)), np.zeros((len(T), 2))
s = list(kt.splits(d))
for f, tr, va in s:
    sc = StandardScaler().fit(X[tr])
    m = LogisticRegression(max_iter=500).fit(sc.transform(X[tr]), y[tr])
    oof[va] = m.predict_proba(sc.transform(X[va])); test += m.predict_proba(sc.transform(T)) / len(s)
kt.save(d, oof, test, notes={"model": "logistic"})
'''),
    ("GBDT plus engineered interaction and in-fold target encoding", '''
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from kaggle_agent import toolkit as kt
d = kt.load()
tr_df, te_df, y = d["train"], d["test"], d["y"]
def base(f):
    out = f[["x1", "x2", "x3", "x4"]].copy()
    out["x1x2"] = f["x1"] * f["x2"]
    out["x3sq"] = f["x3"] ** 2
    return out
X, T = base(tr_df), base(te_df)
oof, test = np.zeros((len(y), 2)), np.zeros((len(T), 2))
s = list(kt.splits(d))
iters = 20 if d["smoke"] else 300
for f, tr, va in s:
    # target encoding of the high-cardinality city column, fit on training rows only
    stats = tr_df.iloc[tr].assign(t=y[tr]).groupby("city")["t"].agg(["sum", "count"])
    prior = y[tr].mean()
    enc = lambda col: ((stats["sum"] + 20 * prior) / (stats["count"] + 20)).reindex(col).fillna(prior).to_numpy()
    Xtr, Xva, Xte = X.iloc[tr].assign(city=enc(tr_df["city"].iloc[tr])), X.iloc[va].assign(city=enc(tr_df["city"].iloc[va])), T.assign(city=enc(te_df["city"]))
    m = HistGradientBoostingClassifier(max_iter=iters, learning_rate=.05, max_leaf_nodes=15, min_samples_leaf=40,
                                       random_state=d["seed"]).fit(Xtr, y[tr])
    oof[va] = m.predict_proba(Xva); test += m.predict_proba(Xte) / len(s)
kt.save(d, oof, test, notes={"model": "hist", "features": "x1*x2, x3^2, in-fold target-encoded city"})
'''),
]


def make_competition(directory, n=6000, seed=0):
    import numpy as np
    import pandas as pd
    rng = np.random.default_rng(seed)
    city_effect = rng.normal(0, 1.2, 300)
    def frame(rows, prefix):
        x = rng.normal(size=(4, rows))
        city = rng.integers(0, 300, rows)
        logit = 1.8 * x[0] * x[1] + .8 * (x[2] ** 2 - 1) + .3 * x[3] + city_effect[city]
        y = np.where(rng.random(rows) < 1 / (1 + np.exp(-logit)), "yes", "no")
        return pd.DataFrame({"id": [f"{prefix}{i}" for i in range(rows)], "x1": x[0], "x2": x[1], "x3": x[2], "x4": x[3],
                             "city": [f"c{c}" for c in city], "y": y})
    (directory / "data").mkdir(parents=True)
    frame(n, "r").to_csv(directory / "data/train.csv", index=False)
    frame(n // 3, "t").drop(columns="y").to_csv(directory / "data/test.csv", index=False)


def realistic_benchmark(output):
    import argparse
    import tempfile
    from kaggle_agent.__main__ import main as cli, run
    from kaggle_agent.agents.base import MockCoder
    from kaggle_agent.storage.database import Store
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    with tempfile.TemporaryDirectory(prefix="kaggle realistic ") as temp:
        temp = Path(temp)
        for mode in ("propose", "code"):
            directory, db = temp / mode, temp / f"{mode}.sqlite3"
            make_competition(directory)
            import contextlib, io
            with contextlib.redirect_stdout(io.StringIO()):
                cli(["--db", str(db), "init", "--competition", str(directory), "--task", "classification",
                     "--train", str(directory / "data/train.csv"), "--test", str(directory / "data/test.csv"),
                     "--target", "y", "--metric", "log_loss", "--folds", "5"])
            path = directory / ".kaggle-agent/profile.json"
            profile = json.loads(path.read_text())
            profile["rules_reviewed"] = True
            path.write_text(json.dumps(profile))
            agent = MockCoder(BENCH_SCRIPTS) if mode == "code" else None
            args = argparse.Namespace(competition=str(directory), agent="mock", mode=mode, execute=True, subscription_confirmed=False,
                                      campaigns=1, trials=len(BENCH_SCRIPTS) if mode == "code" else 4, seconds=None, memory_mb=None,
                                      config=None, command="start", mock_agent=agent)
            start = time.monotonic()
            result = run(args, Store(db))
            seconds = time.monotonic() - start
            store = Store(db)
            full = store.rows("SELECT result,metadata FROM experiments WHERE fidelity='full' AND state='COMPLETED'")
            scores = sorted((sum(json.loads(r["result"])["fold_scores"]) / len(json.loads(r["result"])["fold_scores"]),
                             json.loads(r["result"]).get("score_type"), json.loads(r["metadata"]).get("hypothesis", "")) for r in full)
            rows.append(dict(mode=mode, seconds=round(seconds, 1), full_runs=len(full),
                             best_log_loss=scores[0][0] if scores else None, best=scores[0][2] if scores else None,
                             all=[dict(log_loss=round(s, 5), type=t, hypothesis=h[:80]) for s, t, h in scores], state=result.get("state")))
    report = dict(kind="realistic_mode_comparison", rows_train=6000, folds=5, metric="log_loss (lower is better)", results=rows,
                  limitations=["Synthetic data with a known interaction and a high-cardinality category",
                               "Code mode used two hand-written scripts via a mock coder: it shows what the mode can express, not LLM quality",
                               "Propose mode used its default four-family cycle with the mock proposer",
                               "No real Kaggle data, leaderboard, inference or cost measured"])
    atomic_write(output / "realistic-benchmark.json", json.dumps(report, indent=2))
    return report
