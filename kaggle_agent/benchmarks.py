"""Eight tiny synthetic tasks. No historical ranking or agent-cost claims."""
import json
from pathlib import Path
import time
from kaggle_agent.pipelines.tabular import make_folds,cv_predict
from kaggle_agent.pipelines.optimization import solve_knapsack,check_knapsack
from kaggle_agent.pipelines.forecasting import rolling_origin
from kaggle_agent.evaluation.validation import evaluate
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
    if task in {"classification","regression"}:
        prediction=cv_predict(data["X"],data["y"],data["folds"],data["test_X"],task=task,
                              family=config.get("family","linear"),seed=seed,categorical=data.get("categorical",()),
                              parameters=config.get("parameters"),**config.get("options",{}))
        result=evaluate(data["ids"],data["y"],data["folds"],data["ids"],prediction["oof"],config["metric"])
        return dict(ids=data["ids"],predictions=prediction["oof"],test_ids=data["test_ids"],test_predictions=prediction["test"],fold_scores=result["fold_scores"],score_type="base_oof")
    if task=="optimization":
        result=solve_knapsack(data["weights"],data["values"],data["capacity"],seed=seed,
                              iterations=config.get("iterations",100),operator=config.get("operator","anneal"))
        return result|dict(fold_scores=[result["score"]],score_type="exact")
    return rolling_origin(data["values"],data["times"],data["origins"],data["horizon"],season=data["season"],
                          family=config.get("family","seasonal_naive"),metric=config["metric"])


def benchmark(output,seeds=(11,29)):
    rows=[]
    for task in ("classification","regression","optimization","forecasting"):
        for seed in seeds:
            data=synthetic(task,seed)
            for variant in ("original_baseline","upgraded"):
                # A reproducible baseline proxy; the original repo had no executable
                # agent runner. This is NOT a measurement of original agent behavior.
                config=dict(seed=seed,metric="log_loss" if task=="classification" else "rmse")
                if task=="optimization":config["operator"]="greedy" if variant=="original_baseline" else "anneal"
                elif task=="forecasting":config["family"]="seasonal_naive" if variant=="original_baseline" else "lag_ridge"
                elif variant=="upgraded":config["family"]="forest"
                start=time.monotonic();result=run_dataset(data,config)
                rows.append(dict(task=task,seed=seed,variant=variant,seconds=time.monotonic()-start,
                                 fold_scores=result["fold_scores"],complete=True,cost_cents=0,
                                 tokens=None,interventions=0,config=config))
    report=dict(kind="synthetic_pipeline_comparison",tasks=8,runs=len(rows),rows=rows,
                limitations=["Original agent runner absent: baseline is a proxy, not measured original agent performance",
                             "No paid inference or cloud jobs; token metrics unavailable",
                             "Synthetic tasks do not establish medal or private leaderboard performance",
                             "Trials matched by task/seed and one model configuration; wall times measured, not artificially equalized"])
    atomic_write(Path(output)/"benchmark.json",json.dumps(report,indent=2))
    return report
