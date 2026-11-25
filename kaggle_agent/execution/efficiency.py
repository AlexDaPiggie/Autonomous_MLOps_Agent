"""Progressive fidelity, deterministic bounded trials, immutable cache identities."""
import itertools
import json
from pathlib import Path
import time
from kaggle_agent.execution.gates import require
from kaggle_agent.storage.database import fingerprint,checksum
from kaggle_agent.storage.export_state import atomic_write

STAGES=("smoke","screen","intermediate","full","ensemble")


def next_fidelity(stage,passed,*,explore=False):
    require(stage in STAGES,"Unknown fidelity")
    if not passed and not explore:return None
    i=STAGES.index(stage)
    return STAGES[i+1] if i+1<len(STAGES) else None


def bounded_search(space,objective,*,max_trials=4,seconds=60,direction="minimize"):
    require(0<max_trials<=100 and 0<seconds<=1800 and direction in {"minimize","maximize"},"Invalid search bounds")
    started=time.monotonic();results=[]
    keys=sorted(space)
    for values in itertools.product(*(space[k] for k in keys)):
        if len(results)>=max_trials or time.monotonic()-started>=seconds:break
        config=dict(zip(keys,values));score=objective(config)
        import math
        require(math.isfinite(score),"Nonfinite search score")
        results.append(dict(config=config,score=score))
    return sorted(results,key=lambda r:r["score"],reverse=direction=="maximize")


def fidelity_agreement(low,full):
    require(set(low)==set(full) and len(low)>=2,"Need matched fidelity candidates")
    from scipy.stats import spearmanr
    keys=sorted(low)
    result=spearmanr([low[k] for k in keys],[full[k] for k in keys])
    return dict(spearman=float(result.statistic),candidates=len(keys),
                limitation="Heuristic screen; preserve exploration when rank agreement is weak")


def optuna_search(space,objective,*,max_trials=4,seconds=60,seed=42,direction="minimize"):
    require(0<max_trials<=100 and 0<seconds<=1800,"Invalid Optuna bounds")
    import optuna
    study=optuna.create_study(direction=direction,sampler=optuna.samplers.TPESampler(seed=seed))
    def trial_objective(trial):
        config={key:trial.suggest_categorical(key,values) for key,values in sorted(space.items())}
        return objective(config)
    study.optimize(trial_objective,n_trials=max_trials,timeout=seconds,n_jobs=1)
    return dict(parameters=study.best_params,score=study.best_value,trials=len(study.trials))


class Cache:
    def __init__(self,directory):self.directory=Path(directory)

    def key(self,*,data_hash,split_hash,config,code_hash,seed,evaluator_hash):
        return fingerprint(dict(data_hash=data_hash,split_hash=split_hash,config=config,code_hash=code_hash,seed=seed,evaluator_hash=evaluator_hash))

    def put(self,key,value):
        text=json.dumps(value,sort_keys=True,allow_nan=False)
        atomic_write(self.directory/(key+".json"),text)
        atomic_write(self.directory/(key+".sha256"),checksum(self.directory/(key+".json")))

    def get(self,key):
        path=self.directory/(key+".json");digest=self.directory/(key+".sha256")
        if not path.is_file() or not digest.is_file():return None
        require(checksum(path)==digest.read_text(),"Cache modified; recompute")
        return json.loads(path.read_text())
