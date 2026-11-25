"""Assess a frozen prediction library without retraining base models."""
import json
from pathlib import Path
from kaggle_agent.execution.gates import require
from kaggle_agent.storage.database import checksum,fingerprint
from .ensemble import conditional_blend


def assess(data,sources,metric,baseline_index=0):
    require(data["task"] in {"classification","regression"},"Blending supported for tabular tasks")
    require(1<=len(sources)<=5 and 0<=baseline_index<len(sources),"Bound library to at most five compatible bases")
    library=[]
    for source in sources:
        require(checksum(source["path"])==source["sha256"],"Frozen base predictions changed")
        artifact=json.loads(Path(source["path"]).read_text(encoding="utf-8"))
        require(artifact["score_type"]=="base_oof","Only ordinary base OOF inputs allowed")
        library.append(dict(ids=artifact["ids"],predictions=artifact["predictions"],test_ids=artifact["test_ids"],test_predictions=artifact["test_predictions"],
                            folds=data["folds"],data_hash=fingerprint(dict(ids=data["ids"],y=data["y"])),
                            split_hash=fingerprint(dict(ids=data["ids"],folds=data["folds"])),
                            class_order=sorted(set(data["y"])) if data["task"]=="classification" else [],scale="probability" if data["task"]=="classification" else "target",
                            score_type="base_oof",complete=True,leakage_reviewed=True))
    classification=data["task"]=="classification"
    baseline=conditional_blend([library[baseline_index]],data["y"],metric,classification=classification)
    result=conditional_blend(library,data["y"],metric,classification=classification)
    return result|dict(ids=data["ids"],ensemble_baseline_scores=baseline["fold_scores"])


def assess_tables(root,spec,task,sources,metric,baseline_index=0):
    """Blend registered full OOF runs on real tables.

    Two combiners are scored by held-out meta-CV on the frozen folds: a
    regularized stacker (logistic/ridge) and hill climbing. The better one is
    kept; the single-base combiner on the same folds is the paired baseline.
    """
    import numpy as np
    from kaggle_agent import data as tables
    from .ensemble import conditional_hill_climb,hill_climb_weights
    from .validation import direction,metric_score
    require(2<=len(sources)<=10 and 0<=baseline_index<len(sources),"Blend 2..10 registered runs")
    ids,y,folds=tables.labels(root,spec,task)
    scored=np.asarray(folds)!=-1
    y=np.asarray(y)[scored];folds=np.asarray(folds)[scored]
    oofs=[];tests=[]
    for source in sources:
        require(checksum(source["path"])==source["sha256"],"Frozen base predictions changed")
        oof,test=tables.oof_matrix(root,spec,task,Path(source["path"]).parent)
        oofs.append(oof[scored]);tests.append(test)
    classification=task=="classification"
    way=direction(metric)
    def stacker(arrays,test_arrays):
        from sklearn.linear_model import LogisticRegression,Ridge
        prep=(lambda p:np.log(np.clip(p,1e-6,1-1e-6))) if classification else (lambda p:p)
        X=np.column_stack([prep(a) if a.ndim>1 else prep(a)[:,None] for a in arrays])
        T=np.column_stack([prep(a) if a.ndim>1 else prep(a)[:,None] for a in test_arrays])
        out=np.zeros_like(arrays[0],dtype=float);scores=[]
        make=lambda:LogisticRegression(max_iter=500,random_state=0) if classification else Ridge(alpha=1.)
        for fold in sorted(set(folds.tolist())):
            train=folds!=fold;valid=folds==fold
            model=make().fit(X[train],y[train])
            out[valid]=model.predict_proba(X[valid]) if classification else model.predict(X[valid])
            scores.append(metric_score(metric,y[valid].tolist(),out[valid].tolist()))
        model=make().fit(X,y)
        test=model.predict_proba(T) if classification else model.predict(T)
        return dict(oof=out,fold_scores=scores,test=test)
    base=stacker([oofs[baseline_index]],[tests[baseline_index]])
    stack=stacker(oofs,tests)
    climb=conditional_hill_climb(oofs,y,folds,metric,way)
    climb["test"]=np.tensordot(np.asarray(climb["weights"]),np.stack(tests),axes=1)
    sign=1 if way=="maximize" else -1
    pick=max((("stacker",stack),("hill_climb",climb)),key=lambda item:sign*np.mean(item[1]["fold_scores"]))
    name,chosen=pick
    return dict(oof=chosen["oof"],test=chosen["test"],fold_scores=chosen["fold_scores"],
                ensemble_baseline_scores=base["fold_scores"],combiner=name,
                candidates=dict(stacker=stack["fold_scores"],hill_climb=climb["fold_scores"]),
                weights=climb["weights"],scored_ids=[i for i,s in zip(ids,scored.tolist()) if s],
                limitation="Combiner chosen between two using these meta-CV folds: slightly optimistic")
