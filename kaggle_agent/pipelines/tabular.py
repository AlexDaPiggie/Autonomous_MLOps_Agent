"""CPU-first sklearn pipelines; optional boosting families loaded only on demand."""
from pathlib import Path
from kaggle_agent.execution.gates import require


# Extra hyperparameters each family accepts (validated in gates.validate_config).
FAMILY_PARAMETERS = {
    "linear": {"alpha", "C", "class_weight"},
    "forest": {"iterations", "max_depth", "min_samples_leaf", "max_features"},
    "hist": {"iterations", "learning_rate", "max_leaf_nodes", "max_depth", "min_samples_leaf", "l2_regularization"},
    "catboost": {"iterations", "learning_rate", "depth", "l2_leaf_reg"},
    "lightgbm": {"iterations", "learning_rate", "num_leaves", "max_depth", "min_child_samples",
                 "subsample", "colsample_bytree", "reg_alpha", "reg_lambda"},
    "xgboost": {"iterations", "learning_rate", "max_depth", "min_child_weight", "subsample",
                "colsample_bytree", "reg_alpha", "reg_lambda"},
}


def threads():
    import os
    return max(1, int(os.environ.get("KAGGLE_AGENT_THREADS", "1")))


def make_model(task,family="linear",seed=42,*,categorical=(),interactions=False,calibrate=False,target_log=False,parameters=None):
    from sklearn.compose import ColumnTransformer,TransformedTargetRegressor
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder,OrdinalEncoder,StandardScaler,PolynomialFeatures
    from sklearn.linear_model import LogisticRegression,Ridge
    from sklearn.ensemble import RandomForestClassifier,RandomForestRegressor,HistGradientBoostingClassifier,HistGradientBoostingRegressor
    import numpy as np
    require(task in {"classification","regression"},"Invalid tabular task")
    classification=task=="classification"
    p=dict(parameters or {})
    n_jobs=threads()
    linear=family=="linear"
    # Linear models need scaling and one-hot; trees do better (and use far less
    # memory) with raw numerics and ordinal-coded categories.
    numeric_steps=[("impute",SimpleImputer(strategy="median"))]+([("scale",StandardScaler())] if linear else [])
    transforms=[("numeric",Pipeline(numeric_steps),[i for i in range(p.get("n_features",1)) if i not in categorical])]
    if categorical:
        encoder=(OneHotEncoder(handle_unknown="ignore",sparse_output=False,max_categories=50) if linear else
                 OrdinalEncoder(handle_unknown="use_encoded_value",unknown_value=-1,encoded_missing_value=-1))
        transforms.append(("categorical",Pipeline([("impute",SimpleImputer(strategy="most_frequent")),("encode",encoder)]),list(categorical)))
    prep=ColumnTransformer(transforms)
    iterations=p.get("iterations",30)
    if family=="linear":
        estimator=(LogisticRegression(max_iter=1000,random_state=seed,C=p.get("C",1.),class_weight=p.get("class_weight"))
                   if classification else Ridge(alpha=p.get("alpha",1.)))
    elif family=="forest":
        estimator=(RandomForestClassifier if classification else RandomForestRegressor)(
            n_estimators=iterations,max_depth=p.get("max_depth",6),min_samples_leaf=p.get("min_samples_leaf",1),
            max_features=p.get("max_features","sqrt" if classification else 1.0),n_jobs=n_jobs,random_state=seed)
    elif family=="hist":
        estimator=(HistGradientBoostingClassifier if classification else HistGradientBoostingRegressor)(
            max_iter=iterations,learning_rate=p.get("learning_rate",.1),max_leaf_nodes=p.get("max_leaf_nodes",15),
            max_depth=p.get("max_depth"),min_samples_leaf=p.get("min_samples_leaf",20),
            l2_regularization=p.get("l2_regularization",0.),random_state=seed,early_stopping=False)
    elif family=="catboost":
        from catboost import CatBoostClassifier,CatBoostRegressor
        estimator=(CatBoostClassifier if classification else CatBoostRegressor)(
            iterations=iterations,learning_rate=p.get("learning_rate"),depth=p.get("depth",6),l2_leaf_reg=p.get("l2_leaf_reg",3),
            random_seed=seed,verbose=False,thread_count=n_jobs,allow_writing_files=False)
    elif family=="lightgbm":
        from lightgbm import LGBMClassifier,LGBMRegressor
        subsample=p.get("subsample",1.)
        estimator=(LGBMClassifier if classification else LGBMRegressor)(
            n_estimators=iterations,learning_rate=p.get("learning_rate",.1),num_leaves=p.get("num_leaves",31),
            max_depth=p.get("max_depth",-1),min_child_samples=p.get("min_child_samples",20),subsample=subsample,
            subsample_freq=1 if subsample<1 else 0,colsample_bytree=p.get("colsample_bytree",1.),
            reg_alpha=p.get("reg_alpha",0.),reg_lambda=p.get("reg_lambda",0.),random_state=seed,n_jobs=n_jobs,verbosity=-1)
    elif family=="xgboost":
        from xgboost import XGBClassifier,XGBRegressor
        estimator=(XGBClassifier if classification else XGBRegressor)(
            n_estimators=iterations,learning_rate=p.get("learning_rate",.3),max_depth=p.get("max_depth",3),
            min_child_weight=p.get("min_child_weight",1),subsample=p.get("subsample",1.),
            colsample_bytree=p.get("colsample_bytree",1.),reg_alpha=p.get("reg_alpha",0.),reg_lambda=p.get("reg_lambda",1.),
            random_state=seed,n_jobs=n_jobs)
    else:raise ValueError("Unsupported model family")
    steps=[("preprocess",prep)]
    if interactions:steps.append(("interactions",PolynomialFeatures(degree=2,interaction_only=True,include_bias=False)))
    steps.append(("model",estimator))
    model=Pipeline(steps)
    if classification and calibrate:
        from sklearn.calibration import CalibratedClassifierCV
        model=CalibratedClassifierCV(model,cv=3)
    if not classification and target_log:
        model=TransformedTargetRegressor(regressor=model,func=np.log1p,inverse_func=np.expm1,check_inverse=True)
    return model


def cv_predict(X,y,folds,test_X,*,task,family="linear",seed=42,categorical=(),parameters=None,seeds=1,full_refit=False,**options):
    """Fixed-fold OOF and test predictions.

    seeds>1 averages several seeds (OOF and test). full_refit=True makes the
    test prediction from models refit on 100% of scored rows instead of the
    fold-model average. Fold -1 rows (time scheme) train every fold, never scored.
    """
    import numpy as np
    require(type(seeds) is int and 1<=seeds<=20,"seeds must be 1..20")
    X=np.asarray(X,dtype=object if categorical else float);y=np.asarray(y);folds=np.asarray(folds)
    test_X=np.asarray(test_X,dtype=object if categorical else float)
    scored=sorted(set(folds.tolist())-{-1})
    require(len(X)==len(y)==len(folds) and len(scored)>=2,"Need fixed CV folds")
    if task=="classification":
        classes=np.unique(y);require(list(classes)==list(range(len(classes))),"Classification labels must be encoded 0..K-1")
        oof=np.zeros((len(y),len(classes)));test=np.zeros((len(test_X),len(classes)))
    else:oof=np.zeros(len(y));test=np.zeros(len(test_X))
    def build(run_seed):
        return make_model(task,family,run_seed,categorical=categorical,parameters=(parameters or {})|dict(n_features=X.shape[1]),**options)
    def predict(model,rows):
        return model.predict_proba(rows) if task=="classification" else model.predict(rows)
    for offset in range(seeds):
        run_seed=seed+offset
        for fold in scored:
            # Time scheme: train only on earlier blocks (fold -1 and smaller folds).
            train=(folds<fold) if -1 in folds else (folds!=fold)
            valid=folds==fold
            model=build(run_seed)
            if options.get("target_log"):require(bool(np.all(y[train]>-1)),"log1p target domain violation")
            model.fit(X[train],y[train])
            if task=="classification":require(list(model.classes_)==list(classes),"Class missing in training fold")
            oof[valid]+=predict(model,X[valid])/seeds
            if not full_refit:test+=predict(model,test_X)/(seeds*len(scored))
        if full_refit:
            model=build(run_seed);model.fit(X,y);test+=predict(model,test_X)/seeds
    keep=folds!=-1
    return dict(oof=oof.tolist(),test=test.tolist(),seed=seed,scored=keep.tolist())


def validate_group_folds(groups,folds):
    require(len(groups)==len(folds),"Group/fold length mismatch")
    mapping={}
    for group,fold in zip(groups,folds):
        require(group not in mapping or mapping[group]==fold,"Group leakage across folds")
        mapping[group]=fold


def make_folds(y,*,task,n_splits=3,seed=42,groups=None):
    import numpy as np
    from sklearn.model_selection import StratifiedKFold,KFold,GroupKFold
    y=np.asarray(y);folds=np.full(len(y),-1)
    splitter=(GroupKFold(n_splits=n_splits) if groups is not None else
              StratifiedKFold(n_splits=n_splits,shuffle=True,random_state=seed) if task=="classification" else
              KFold(n_splits=n_splits,shuffle=True,random_state=seed))
    for fold,(_,valid) in enumerate(splitter.split(np.zeros(len(y)),y,groups)):
        folds[valid]=fold
    return folds.tolist()


def fold_target_encode(train_values,train_y,valid_values,smoothing=10):
    """Call inside each training fold; validation labels aren't accepted."""
    import numpy as np
    require(len(train_values)==len(train_y)>0 and smoothing>0,"Invalid encoding inputs")
    global_mean=float(np.mean(train_y));stats={}
    for key,value in zip(train_values,train_y):
        total,count=stats.get(key,(0.,0));stats[key]=(total+value,count+1)
    return [(stats[v][0]+smoothing*global_mean)/(stats[v][1]+smoothing) if v in stats else global_mean for v in valid_values]


def run_tables(data_root,spec,task,metric,config,out_dir):
    """Propose-mode run on real tables: documented families on all non-id/target columns."""
    import numpy as np
    from kaggle_agent import data as tables
    train=tables.read_table(tables.resolve(data_root,spec,"train"))
    test=tables.read_table(tables.resolve(data_root,spec,"test"))
    ids,y,folds=tables.labels(data_root,spec,task)
    require(train[spec["id_column"]].astype(str).tolist()==ids,"Train order changed while reading")
    columns=[c for c in train.columns if c not in {spec["id_column"],spec["target_column"]}]
    require(set(columns)<=set(test.columns),"Test is missing feature columns")
    from pandas.api.types import is_numeric_dtype
    categorical=tuple(i for i,c in enumerate(columns) if not is_numeric_dtype(train[c]))
    prediction=cv_predict(train[columns].to_numpy(),y,folds,test[columns].to_numpy(),task=task,
                          family=config.get("family","linear"),seed=config.get("seed",42),categorical=categorical,
                          parameters=config.get("parameters"),seeds=config.get("seeds",1),
                          full_refit=config.get("full_refit",False),**config.get("options",{}))
    keep=np.asarray(prediction["scored"])
    tables.write_predictions(Path(out_dir)/"oof.csv",np.asarray(ids)[keep],np.asarray(prediction["oof"])[keep])
    tables.write_predictions(Path(out_dir)/"test.csv",tables.test_ids(data_root,spec),prediction["test"])
    return tables.score(data_root,spec,task,metric,out_dir)
