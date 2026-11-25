"""Independent metric and alignment checks; explicit frozen evaluation identities."""
import json
import math
import statistics
from kaggle_agent.execution.gates import require
from kaggle_agent.storage.database import fingerprint, checksum


CLASSIFICATION_METRICS={"accuracy","balanced_accuracy","log_loss","roc_auc","map3"}
MAXIMIZE={"accuracy","balanced_accuracy","roc_auc","map3","r2","objective"}


def direction(metric):
    """Metric direction for automatic blending; profiles still state theirs explicitly."""
    return "maximize" if metric in MAXIMIZE else "minimize"


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
    if metric in CLASSIFICATION_METRICS:
        require(p.ndim==2 and p.shape[1]>=2,"Classification requires ordered class probabilities")
        require(bool(np.all((p>=0)&(p<=1))) and bool(np.allclose(p.sum(axis=1),1,atol=1e-4)),"Invalid probabilities")
        if metric=="accuracy":return float(metrics.accuracy_score(y,p.argmax(axis=1)))
        if metric=="balanced_accuracy":return float(metrics.balanced_accuracy_score(y,p.argmax(axis=1)))
        if metric=="log_loss":return float(metrics.log_loss(y,p,labels=list(range(p.shape[1]))))
        if metric=="map3":
            top=np.argsort(-p,axis=1,kind="stable")[:,:3]
            hits=(top==y[:,None])
            return float(np.mean((hits/np.arange(1,top.shape[1]+1)).sum(axis=1)))
        return float(metrics.roc_auc_score(y,p[:,1] if p.shape[1]==2 else p,multi_class="ovr"))
    require(p.ndim==1,"Regression predictions must be one dimensional")
    if metric=="rmse":return float(np.sqrt(metrics.mean_squared_error(y,p)))
    if metric=="mae":return float(metrics.mean_absolute_error(y,p))
    if metric=="r2":return float(metrics.r2_score(y,p))
    if metric=="rmsle":
        require(bool(np.all(y>-1)) and bool(np.all(p>-1)),"RMSLE needs values above -1")
        return float(np.sqrt(metrics.mean_squared_log_error(y,p)))
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
        require("dataset_path" in meta or "data_spec" in meta,"Frozen dataset provenance required for promotion")
        predictions=db.execute("SELECT * FROM predictions WHERE experiment=?",(experiment,)).fetchall()
        require(bool(predictions),"Registered prediction artifacts required")
        for prediction in predictions:
            require(checksum(prediction["path"])==prediction["checksum"],"Prediction artifact changed after evaluation")
        from pathlib import Path
        independently_score(meta,Path(predictions[0]["path"]).parent)
        require(not ensemble or result.get("score_type") in {"conditional_meta_cv","nested"},"Ensemble needs held-out meta-validation")
        if ensemble:
            require("ensemble_baseline_scores" in result,"Paired baseline combiner must use identical meta folds")
            contribution=paired_improvement(result["fold_scores"],result["ensemble_baseline_scores"],json.loads(comp["profile"])["direction"],margin)
            if not contribution["improved"]:return contribution
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
    if "data_spec" in metadata:
        return independently_score_tables(metadata,root)
    data_path=Path(metadata["dataset_path"])
    require(checksum(data_path)==metadata["dataset_checksum"],"Frozen dataset changed")
    require(evaluator_version()==metadata["evaluator_hash"],"Evaluator source changed")
    data=json.loads(data_path.read_text(encoding="utf-8"))
    artifact=json.loads((Path(root)/"predictions.json").read_text(encoding="utf-8"))
    if metadata["config"].get("blend_sources"):
        from .assessment import assess
        import numpy as np
        expected=assess(data,metadata["config"]["blend_sources"],metadata["metric"],metadata["config"].get("baseline_index",0))
        require(bool(np.allclose(expected["predictions"],artifact["predictions"],rtol=0,atol=1e-10)),"Meta-validation implementation mismatch")
        require(expected["ensemble_baseline_scores"]==artifact["ensemble_baseline_scores"],"Baseline combiner must use identical permitted rows")
    if data["task"] in {"classification","regression"}:
        result=evaluate(data["ids"],data["y"],data["folds"],artifact["ids"],artifact["predictions"],metadata["metric"])
        aligned(artifact["test_ids"],artifact["test_predictions"],data["test_ids"])
        require(finite(artifact["test_predictions"]),"Nonfinite test prediction")
        require(fingerprint(data)==metadata["data_hash"] and result["split_hash"]==metadata["split_hash"],"Frozen evaluation identity mismatch")
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


def independently_score_tables(metadata,root):
    """Real-table and plugin runs: frozen files, evaluator and (for optimization) scorer."""
    from pathlib import Path
    from kaggle_agent import data as tables
    spec=metadata["data_spec"];data_root=Path(metadata["data_root"])
    require(evaluator_version()==metadata["evaluator_hash"],"Evaluator source changed")
    if spec.get("kind")=="optimization":
        from kaggle_agent.pipelines.plugin import identity,score_solution
        current=identity(data_root,spec)
        require(current["data_hash"]==metadata["data_hash"] and current["split_hash"]==metadata["split_hash"],"Frozen data or scorer changed")
        return [score_solution(data_root,spec,Path(root)/spec["solution_name"])]
    current=tables.identity(data_root,spec)
    require(current["data_hash"]==metadata["data_hash"] and current["split_hash"]==metadata["split_hash"],"Frozen tables or folds changed")
    if metadata["config"].get("blend_sources"):
        from .assessment import assess_tables
        import numpy as np
        expected=assess_tables(data_root,spec,metadata["task"],metadata["config"]["blend_sources"],metadata["metric"])
        _,oof=tables.read_predictions(Path(root)/"oof.csv",n_classes=len(tables.class_order(data_root,spec)) if metadata["task"]=="classification" else None)
        require(bool(np.allclose(expected["oof"],oof,rtol=0,atol=1e-6)),"Meta-validation implementation mismatch")
    fidelity=metadata["config"].get("_fidelity","full")
    return tables.score(data_root,spec,metadata["task"],metadata["metric"],root,subset=fidelity!="full")
