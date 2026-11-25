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
