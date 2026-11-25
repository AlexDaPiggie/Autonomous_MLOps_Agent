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
