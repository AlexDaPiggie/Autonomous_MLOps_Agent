"""Fixed-library nested stacking: fit base preprocessing and combiner inside outer training."""
from kaggle_agent.execution.gates import require
from kaggle_agent.pipelines.tabular import make_folds,cv_predict
from kaggle_agent.evaluation.validation import evaluate


def nested_stack(X,y,outer_folds,ids,metric,*,task="regression",families=("linear","forest"),seed=42,regularization=1.):
    import numpy as np
    from sklearn.linear_model import Ridge,LogisticRegression
    require(0<len(families)<=3 and regularization>0,"Bound fixed library and regularization")
    X=np.asarray(X);y=np.asarray(y);folds=np.asarray(outer_folds)
    classification=task=="classification"
    out=np.zeros((len(y),len(np.unique(y)))) if classification else np.zeros(len(y))
    for fold in sorted(set(folds)):
        train=folds!=fold;valid=~train
        inner_folds=make_folds(y[train],task=task,n_splits=3,seed=seed)
        libraries=[cv_predict(X[train],y[train],inner_folds,X[valid],task=task,family=family,seed=seed) for family in families]
        if classification:
            fit_X=np.concatenate([np.log(np.clip(r["oof"],1e-6,1-1e-6)) for r in libraries],axis=1)
            predict_X=np.concatenate([np.log(np.clip(r["test"],1e-6,1-1e-6)) for r in libraries],axis=1)
            model=LogisticRegression(C=1/regularization,max_iter=300,random_state=seed)
        else:
            fit_X=np.column_stack([r["oof"] for r in libraries]);predict_X=np.column_stack([r["test"] for r in libraries]);model=Ridge(alpha=regularization)
        model.fit(fit_X,y[train])
        out[valid]=model.predict_proba(predict_X) if classification else model.predict(predict_X)
    result=evaluate(ids,y.tolist(),folds.tolist(),ids,out.tolist(),metric)
    return result|dict(predictions=out.tolist(),score_type="nested",selection_policy="Frozen families/regularization; outer labels excluded from all fitting")
