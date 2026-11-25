"""Rolling-origin univariate forecasts. Exogenous inputs require as-of timestamps."""
from kaggle_agent.execution.gates import require
from kaggle_agent.evaluation.validation import metric_score,finite


def check_temporal(train_times,validation_times,*,feature_available_times=None):
    require(bool(train_times) and bool(validation_times),"Empty temporal split")
    require(max(train_times)<min(validation_times),"Future leakage/overlapping forecast split")
    require(train_times==sorted(set(train_times)) and validation_times==sorted(set(validation_times)),"Duplicate/unsorted timestamps")
    if feature_available_times is not None:
        require(len(feature_available_times)==len(validation_times) and all(t<=max(train_times) for t in feature_available_times),"Unavailable future exogenous feature")


def predict(history,horizon,*,season=1,family="seasonal_naive",lags=6):
    require(horizon>0 and season>0 and len(history)>=season and finite(history),"Invalid forecast history")
    if family=="seasonal_naive":return [float(history[len(history)-season+i%season]) for i in range(horizon)]
    require(family in {"lag_ridge","lag_boosting"} and len(history)>lags+2,"Insufficient history/unknown forecast family")
    from sklearn.linear_model import Ridge
    from sklearn.ensemble import HistGradientBoostingRegressor
    # Training features use only earlier values. Recursive horizon never reads targets.
    X=[history[i-lags:i] for i in range(lags,len(history))];y=history[lags:]
    model=Ridge(alpha=1.) if family=="lag_ridge" else HistGradientBoostingRegressor(max_iter=30,random_state=42,early_stopping=False)
    model.fit(X,y);buffer=list(history);out=[]
    for _ in range(horizon):
        value=float(model.predict([buffer[-lags:]])[0]);buffer.append(value);out.append(value)
    return out


def rolling_origin(values,times,origins,horizon,*,season=1,family="seasonal_naive",metric="rmse"):
    require(len(values)==len(times) and origins==sorted(set(origins)),"Invalid rolling-origin plan")
    require(all(origins[i]+horizon<=origins[i+1] for i in range(len(origins)-1)),"Overlapping scored horizons need explicit weighting")
    scores=[];predictions=[];ids=[];folds=[]
    for fold,origin in enumerate(origins):
        require(0<origin and origin+horizon<=len(values),"Forecast horizon exceeds data")
        check_temporal(times[:origin],times[origin:origin+horizon])
        p=predict(values[:origin],horizon,season=season,family=family)
        scores.append(metric_score(metric,values[origin:origin+horizon],p))
        predictions.extend(p);ids.extend(times[origin:origin+horizon]);folds.extend([fold]*horizon)
    return dict(fold_scores=scores,predictions=predictions,ids=ids,folds=folds,score_type="rolling_origin")
