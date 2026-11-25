"""Conditional meta-CV over a frozen prediction library, not full nested evaluation."""
from .validation import aligned, evaluate
from kaggle_agent.execution.gates import require


def validate_library(candidates):
    require(bool(candidates),"Empty library")
    reference=candidates[0]
    keys=("data_hash","split_hash","class_order","scale","score_type")
    for candidate in candidates:
        require(all(candidate.get(k)==reference.get(k) for k in keys),"Incompatible prediction provenance")
        require(candidate.get("complete") is True and candidate.get("leakage_reviewed") is True,"Incomplete/unreviewed provenance")
        require(candidate.get("folds")==reference.get("folds"),"Prediction fold mismatch")
        require(candidate["score_type"]=="base_oof","Meta-validation needs base OOF library")
        aligned(candidate["ids"],candidate["predictions"],reference["ids"])


def conditional_blend(candidates,y,metric,*,classification=False,regularization=1.):
    import numpy as np
    from sklearn.linear_model import LogisticRegression,Ridge
    validate_library(candidates)
    require(regularization>0,"Positive regularization required")
    ids=candidates[0]["ids"];folds=np.asarray(candidates[0]["folds"])
    arrays=[np.asarray(aligned(c["ids"],c["predictions"],ids)) for c in candidates]
    if classification:
        features=np.concatenate([np.log(np.clip(p,1e-6,1-1e-6)) for p in arrays],axis=1)
        classes=np.unique(y);require(list(classes)==list(range(len(classes))),"Class labels must be ordered integer indices")
        predictions=np.zeros_like(arrays[0],dtype=float)
    else:
        features=np.column_stack(arrays);predictions=np.zeros(len(y))
    y=np.asarray(y)
    for fold in sorted(set(folds)):
        train=folds!=fold;valid=~train
        model=(LogisticRegression(C=1/regularization,max_iter=300,random_state=0) if classification else Ridge(alpha=regularization))
        model.fit(features[train],y[train])
        if classification:
            require(list(model.classes_)==list(classes),"Class missing in meta-training fold")
            predictions[valid]=model.predict_proba(features[valid])
        else:predictions[valid]=model.predict(features[valid])
    result=evaluate(ids,y.tolist(),folds.tolist(),ids,predictions.tolist(),metric)
    result.update(predictions=predictions.tolist(),score_type="conditional_meta_cv",
                  limitation="Library was selected using these OOF labels; not independent nested pipeline validation",
                  correlations=np.corrcoef(np.column_stack([p[:,1] if p.ndim==2 else p for p in arrays]),rowvar=False).tolist() if len(arrays)>1 else [[1.]])
    if all("test_predictions" in candidate for candidate in candidates):
        test_ids=candidates[0]["test_ids"]
        tests=[np.asarray(aligned(c["test_ids"],c["test_predictions"],test_ids)) for c in candidates]
        test_features=np.concatenate([np.log(np.clip(p,1e-6,1-1e-6)) for p in tests],axis=1) if classification else np.column_stack(tests)
        # Full-library refit is for test inference only, never scored as held-out CV.
        final_model=LogisticRegression(C=1/regularization,max_iter=300,random_state=0) if classification else Ridge(alpha=regularization)
        final_model.fit(features,y)
        result["test_predictions"]=(final_model.predict_proba(test_features) if classification else final_model.predict(test_features)).tolist()
        result["test_ids"]=test_ids
    return result


def hill_climb_weights(arrays,y,metric,direction,*,rounds=40):
    """Caruana-style greedy blend: add (with replacement) the model that helps most.

    arrays: list of OOF prediction arrays aligned with y. Returns weights that
    sum to 1. Stops when no addition improves the metric.
    """
    import numpy as np
    from .validation import metric_score
    sign=1 if direction=="maximize" else -1
    counts=np.zeros(len(arrays));blend=None;best=-np.inf
    def value(p):return sign*metric_score(metric,y,p.tolist())
    for _ in range(rounds):
        choice=None
        for k,a in enumerate(arrays):
            n=counts.sum()
            trial=a if blend is None else (blend*n+a)/(n+1)
            v=value(trial)
            if v>best+1e-12:best,choice,candidate=v,k,trial
        if choice is None:break
        counts[choice]+=1;blend=candidate
    return counts/counts.sum()


def conditional_hill_climb(arrays,y,folds,metric,direction,*,rounds=40):
    """Honest hill-climb score: weights fit on other folds, scored on the held-out fold."""
    import numpy as np
    from .validation import metric_score
    y=np.asarray(y);folds=np.asarray(folds);stack=np.stack(arrays)
    oof=np.zeros_like(stack[0],dtype=float);scores=[]
    for fold in sorted(set(folds.tolist())-{-1}):
        train=folds!=fold;valid=folds==fold
        w=hill_climb_weights([a[train] for a in arrays],y[train],metric,direction,rounds=rounds)
        oof[valid]=np.tensordot(w,stack[:,valid],axes=1)
        scores.append(metric_score(metric,y[valid].tolist(),oof[valid].tolist()))
    weights=hill_climb_weights(arrays,y,metric,direction,rounds=rounds)
    return dict(oof=oof,fold_scores=scores,weights=weights.tolist())
