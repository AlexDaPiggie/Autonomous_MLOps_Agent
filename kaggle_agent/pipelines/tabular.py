"""CPU-first sklearn pipelines; optional boosting families loaded only on demand."""
from kaggle_agent.execution.gates import require


def make_model(task,family="linear",seed=42,*,categorical=(),interactions=False,calibrate=False,target_log=False,parameters=None):
    from sklearn.compose import ColumnTransformer,TransformedTargetRegressor
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder,StandardScaler,PolynomialFeatures
    from sklearn.linear_model import LogisticRegression,Ridge
    from sklearn.ensemble import RandomForestClassifier,RandomForestRegressor,HistGradientBoostingClassifier,HistGradientBoostingRegressor
    import numpy as np
    require(task in {"classification","regression"},"Invalid tabular task")
    classification=task=="classification"
    parameters=parameters or {}
    numeric=Pipeline([("impute",SimpleImputer(strategy="median")),("scale",StandardScaler())])
    transforms=[("numeric",numeric,[i for i in range(parameters.get("n_features",1)) if i not in categorical])]
    if categorical:
        transforms.append(("categorical",Pipeline([("impute",SimpleImputer(strategy="most_frequent")),
                          ("encode",OneHotEncoder(handle_unknown="ignore",sparse_output=False))]),list(categorical)))
    prep=ColumnTransformer(transforms)
    if family=="linear":estimator=LogisticRegression(max_iter=500,random_state=seed,class_weight=parameters.get("class_weight")) if classification else Ridge(alpha=parameters.get("alpha",1.))
    elif family=="forest":estimator=(RandomForestClassifier if classification else RandomForestRegressor)(n_estimators=parameters.get("iterations",30),max_depth=parameters.get("max_depth",6),n_jobs=1,random_state=seed)
    elif family=="hist":estimator=(HistGradientBoostingClassifier if classification else HistGradientBoostingRegressor)(max_iter=parameters.get("iterations",30),max_leaf_nodes=parameters.get("max_leaf_nodes",15),random_state=seed,early_stopping=False)
    elif family=="catboost":
        from catboost import CatBoostClassifier,CatBoostRegressor
        estimator=(CatBoostClassifier if classification else CatBoostRegressor)(iterations=parameters.get("iterations",30),random_seed=seed,verbose=False,thread_count=1,allow_writing_files=False)
    elif family=="lightgbm":
        from lightgbm import LGBMClassifier,LGBMRegressor
        estimator=(LGBMClassifier if classification else LGBMRegressor)(n_estimators=parameters.get("iterations",30),random_state=seed,n_jobs=1,verbosity=-1)
    elif family=="xgboost":
        from xgboost import XGBClassifier,XGBRegressor
        estimator=(XGBClassifier if classification else XGBRegressor)(n_estimators=parameters.get("iterations",30),random_state=seed,n_jobs=1,max_depth=parameters.get("max_depth",3))
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


def cv_predict(X,y,folds,test_X,*,task,family="linear",seed=42,categorical=(),parameters=None,**options):
    import numpy as np
    X=np.asarray(X,dtype=object if categorical else float);y=np.asarray(y);folds=np.asarray(folds)
    test_X=np.asarray(test_X,dtype=object if categorical else float)
    require(len(X)==len(y)==len(folds) and len(set(folds))>=2,"Need fixed CV folds")
    if task=="classification":
        classes=np.unique(y);require(list(classes)==list(range(len(classes))),"Classification labels must be encoded 0..K-1")
        oof=np.zeros((len(y),len(classes)));test=np.zeros((len(test_X),len(classes)))
    else:oof=np.zeros(len(y));test=np.zeros(len(test_X))
    for fold in sorted(set(folds)):
        train=folds!=fold;valid=~train
        model=make_model(task,family,seed,categorical=categorical,parameters=(parameters or {})|dict(n_features=X.shape[1]),**options)
        if options.get("target_log"):require(bool(np.all(y[train]>-1)),"log1p target domain violation")
        model.fit(X[train],y[train])
        if task=="classification":
            require(list(model.classes_)==list(classes),"Class missing in training fold")
            oof[valid]=model.predict_proba(X[valid]);test+=model.predict_proba(test_X)
        else:oof[valid]=model.predict(X[valid]);test+=model.predict(test_X)
    return dict(oof=oof.tolist(),test=(test/len(set(folds))).tolist(),seed=seed)


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
