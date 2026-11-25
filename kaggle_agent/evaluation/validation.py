"""Independent metric and alignment checks; explicit frozen evaluation identities."""
import json
import math
import statistics
from kaggle_agent.execution.gates import require
from kaggle_agent.storage.database import fingerprint, checksum


def aligned(ids, predictions, expected_ids):
    require(len(ids)==len(predictions)==len(expected_ids),"Prediction length mismatch")
    require(len(set(ids))==len(ids) and len(set(expected_ids))==len(expected_ids),"Duplicate prediction IDs")
    require(set(ids)==set(expected_ids),"Missing/unexpected prediction IDs")
    by_id=dict(zip(ids,predictions))
    return [by_id[i] for i in expected_ids]


def finite(values):
    if isinstance(values,(list,tuple)):
        return all(finite(x) for x in values)
    return type(values) in (int,float) and math.isfinite(values)


def metric_score(metric,y,predictions):
    import numpy as np
    from sklearn import metrics
    require(finite(predictions),"Nonfinite predictions")
    y=np.asarray(y);p=np.asarray(predictions)
    require(len(y)==len(p) and len(y)>0,"Invalid metric rows")
    if metric in {"accuracy","log_loss","roc_auc"}:
        require(p.ndim==2 and p.shape[1]>=2,"Classification requires ordered class probabilities")
        require(bool(np.all((p>=0)&(p<=1))) and bool(np.allclose(p.sum(axis=1),1)),"Invalid probabilities")
        if metric=="accuracy":return float(metrics.accuracy_score(y,p.argmax(axis=1)))
        if metric=="log_loss":return float(metrics.log_loss(y,p,labels=list(range(p.shape[1]))))
        return float(metrics.roc_auc_score(y,p[:,1] if p.shape[1]==2 else p,multi_class="ovr"))
    require(p.ndim==1,"Regression predictions must be one dimensional")
    if metric=="rmse":return float(np.sqrt(metrics.mean_squared_error(y,p)))
    if metric=="mae":return float(metrics.mean_absolute_error(y,p))
    if metric=="r2":return float(metrics.r2_score(y,p))
    if metric=="mape":
        require(bool(np.all(y!=0)),"MAPE undefined for zero targets")
        return float(np.mean(np.abs((y-p)/y)))
    raise ValueError(f"Unsupported metric {metric}")


def evaluate(ids,y,folds,prediction_ids,predictions,metric,*,expected_folds=None):
    require(len(ids)==len(y)==len(folds),"Evaluation rows mismatch")
    if expected_folds is not None:require(folds==expected_folds,"Wrong folds")
    p=aligned(prediction_ids,predictions,ids)
    require(finite(p),"Nonfinite predictions")
    scores=[]
    for fold in sorted(set(folds)):
        rows=[i for i,f in enumerate(folds) if f==fold]
        scores.append(metric_score(metric,[y[i] for i in rows],[p[i] for i in rows]))
    return dict(fold_scores=scores,mean=statistics.mean(scores),
                std=statistics.stdev(scores) if len(scores)>1 else 0.,
                data_hash=fingerprint(dict(ids=ids,y=y)),split_hash=fingerprint(dict(ids=ids,folds=folds)))


def paired_improvement(candidate,baseline,direction,margin=0.):
    require(direction in {"minimize","maximize"} and margin>=0,"Invalid improvement policy")
    require(len(candidate)==len(baseline)>0 and finite(candidate) and finite(baseline),"Incomparable fold scores")
    sign=1 if direction=="maximize" else -1
    gains=[sign*(a-b) for a,b in zip(candidate,baseline)]
    mean=statistics.mean(gains)
    spread=statistics.stdev(gains) if len(gains)>1 else 0.
    wins=sum(g>margin for g in gains)
    # For five folds preserve existing 4/5 policy; two folds must both win.
    enough_wins=wins >= math.ceil(.8*len(gains))
    return dict(improved=mean>margin and (enough_wins or mean>spread+margin),mean_gain=mean,std_gain=spread,wins=wins)


def promote(store,competition,experiment,*,ensemble=False,margin=0.):
    """Scores must have been independently recomputed before this gate."""
    column="ensemble_champion" if ensemble else "champion"
    with store.transaction() as db:
        comp=db.execute("SELECT * FROM competitions WHERE id=?",(competition,)).fetchone()
        row=db.execute("SELECT * FROM experiments WHERE id=? AND competition=?",(experiment,competition)).fetchone()
        require(row is not None and row["state"]=="COMPLETED" and row["fidelity"]=="full","Only completed full validation can promote")
        result=json.loads(row["result"]);meta=json.loads(row["metadata"])
        require(result.get("independently_scored") is True,"Independent scoring required")
        require("dataset_path" in meta,"Frozen dataset provenance required for promotion")
        predictions=db.execute("SELECT * FROM predictions WHERE experiment=?",(experiment,)).fetchall()
        require(bool(predictions),"Registered prediction artifacts required")
        for prediction in predictions:
            require(checksum(prediction["path"])==prediction["checksum"],"Prediction artifact changed after evaluation")
        from pathlib import Path
        independently_score(meta,Path(predictions[0]["path"]).parent)
        require(not ensemble or result.get("score_type") in {"conditional_meta_cv","nested"},"Ensemble needs held-out meta-validation")
        baseline=comp[column]
        if baseline:
            old=db.execute("SELECT * FROM experiments WHERE id=?",(baseline,)).fetchone()
            previous=json.loads(old["result"]);oldmeta=json.loads(old["metadata"])
            require(all(meta[k]==oldmeta[k] for k in ("data_hash","split_hash","metric","evaluator_hash")),"Incompatible champion validation")
            require(result["score_type"]==previous["score_type"],"Score types cannot be mixed")
            improvement=paired_improvement(result["fold_scores"],previous["fold_scores"],json.loads(comp["profile"])["direction"],margin)
            if not improvement["improved"]:return improvement
        else:improvement=dict(improved=True,reason="first full validated candidate")
        db.execute(f"UPDATE competitions SET {column}=? WHERE id=?",(experiment,competition))
        store.event("champion_promoted",dict(experiment=experiment,ensemble=ensemble,comparison=improvement),competition,db)
        return improvement


def evaluator_version():
    return checksum(__file__)


def independently_score(metadata,root):
    """Recompute from frozen labels/splits and artifact bytes in the parent process."""
    from pathlib import Path
    data_path=Path(metadata["dataset_path"])
    require(checksum(data_path)==metadata["dataset_checksum"],"Frozen dataset changed")
    require(evaluator_version()==metadata["evaluator_hash"],"Evaluator source changed")
    data=json.loads(data_path.read_text(encoding="utf-8"))
    artifact=json.loads((Path(root)/"predictions.json").read_text(encoding="utf-8"))
    if data["task"] in {"classification","regression"}:
        result=evaluate(data["ids"],data["y"],data["folds"],artifact["ids"],artifact["predictions"],metadata["metric"])
        aligned(artifact["test_ids"],artifact["test_predictions"],data["test_ids"])
        require(finite(artifact["test_predictions"]),"Nonfinite test prediction")
        require(result["data_hash"]==metadata["data_hash"] and result["split_hash"]==metadata["split_hash"],"Frozen evaluation identity mismatch")
        return result["fold_scores"]
    if data["task"]=="optimization":
        from kaggle_agent.pipelines.optimization import check_knapsack
        return [check_knapsack(artifact["candidate"],data["weights"],data["values"],data["capacity"])]
    expected_ids=[];folds=[]
    from kaggle_agent.pipelines.forecasting import check_temporal
    for fold,origin in enumerate(data["origins"]):
        check_temporal(data["times"][:origin],data["times"][origin:origin+data["horizon"]])
        expected_ids.extend(data["times"][origin:origin+data["horizon"]]);folds.extend([fold]*data["horizon"])
    labels=dict(zip(data["times"],data["values"]))
    return evaluate(expected_ids,[labels[i] for i in expected_ids],folds,artifact["ids"],artifact["predictions"],metadata["metric"])["fold_scores"]
