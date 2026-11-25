"""Objective checks used before launch and promotion. No arbitrary code execution."""
from datetime import datetime, timezone
import math
from pathlib import Path
from kaggle_agent.storage.database import checksum, fingerprint


class GateError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise GateError(message)


def validate_profile(profile, *, check_deadline=True):
    required = {"task", "metric", "direction", "data_hash", "split_hash", "rules_reviewed",
                "external_resources", "validation", "deadline", "baseline", "constraints"}
    require(required <= profile.keys(), f"Missing profile fields: {sorted(required - profile.keys())}")
    require(profile["task"] in {"classification", "regression", "optimization", "forecasting"}, "Unsupported task")
    require(profile["direction"] in {"minimize", "maximize"}, "Invalid metric direction")
    require(profile["rules_reviewed"] is True, "Competition rules must be reviewed")
    for key in ("data_hash", "split_hash", "metric", "validation"):
        require(bool(profile[key]), f"Missing {key}")
    if profile["deadline"]:
        deadline = datetime.fromisoformat(profile["deadline"])
        require(deadline.tzinfo is not None, "Deadline requires timezone")
        if check_deadline:require(deadline > datetime.now(timezone.utc), "Competition deadline passed")
    return fingerprint(profile)


def experiment_fingerprint(metadata):
    required = {"code_hash", "config", "data_hash", "split_hash", "seed", "metric", "evaluator_hash"}
    require(required <= metadata.keys(), "Incomplete experiment fingerprint")
    return fingerprint({key: metadata[key] for key in sorted(required)})


def prelaunch(profile, metadata, *, smoke_passed, seconds, memory_mb, provider, limits=None):
    from kaggle_agent.supervisor.limits import DEFAULTS
    limits = limits or DEFAULTS
    validate_profile(profile)
    require(provider in {"mock", "local", "script"}, "Paid/remote providers disabled: isolation and authorization required")
    require(smoke_passed is True, "Real-path smoke test required")
    require(0 < seconds <= limits["seconds"] and 0 < memory_mb <= limits["memory_mb"], "Resource caps exceed configured limits")
    require(seconds <= profile["constraints"].get("seconds",limits["seconds"]) and memory_mb <= profile["constraints"].get("memory_mb",limits["memory_mb"]),"Existing stricter resource caps apply")
    require(metadata["data_hash"] == profile["data_hash"] and metadata["split_hash"] == profile["split_hash"], "Data/split mismatch")
    require(metadata["metric"] == profile["metric"], "Metric mismatch")
    validate_config(profile["task"],metadata["config"],max_iterations=limits["max_iterations"])
    return experiment_fingerprint(metadata)


def validate_config(task,config,*,max_iterations=1000):
    require(isinstance(config,dict),"Config must be a JSON object")
    require(type(config.get("seed",42)) is int and 0<=config.get("seed",42)<2**32,"Invalid deterministic seed")
    if config.get("blend_sources"):
        require(task in {"classification","regression"} and 1<=len(config["blend_sources"])<=10,"Invalid bounded blend library")
        return
    if config.get("script_sha256"):
        # Agent-written script: its bytes are fingerprinted; static checks run separately.
        require(isinstance(config["script_sha256"],str) and len(config["script_sha256"])==64,"Invalid script hash")
        return
    if task in {"classification","regression"}:
        from kaggle_agent.pipelines.tabular import FAMILY_PARAMETERS
        family=config.get("family","linear")
        require(family in FAMILY_PARAMETERS,"Unsupported tabular model family")
        params=config.get("parameters") or {}
        require(isinstance(params,dict),"Invalid model parameters")
        unknown=set(params)-FAMILY_PARAMETERS[family]
        require(not unknown,f"Unsupported {family} parameters: {sorted(unknown)}")
        for key,value in params.items():
            if key=="iterations":
                require(type(value) is int and 1<=value<=max_iterations,f"iterations must be 1..{max_iterations} (see limits)")
            elif key=="max_depth" and value is None:
                pass
            elif key in {"max_depth","max_leaf_nodes","num_leaves","depth","min_samples_leaf","min_child_samples"}:
                require(type(value) is int and 1<=value<=100000,f"{key} must be a positive integer")
            elif key in {"learning_rate","subsample","colsample_bytree"}:
                require(type(value) in (int,float) and 0<value<=1,f"{key} must be in (0,1]")
            elif key in {"alpha","C","reg_alpha","reg_lambda","l2_leaf_reg","l2_regularization","min_child_weight"}:
                require(type(value) in (int,float) and 0<=value<=1e6,f"{key} must be in [0,1e6]")
            elif key=="max_features":
                require(value in {"sqrt","log2"} or type(value) in (int,float) and 0<value<=1,"Invalid max_features")
            elif key=="class_weight":
                require(value in {None,"balanced"},"class_weight must be null or balanced")
        options=config.get("options") or {}
        require(isinstance(options,dict) and set(options)<={"interactions","calibrate","target_log"} and all(type(v) is bool for v in options.values()),"Options: interactions, calibrate, target_log (booleans)")
        require(type(config.get("seeds",1)) is int and 1<=config.get("seeds",1)<=20,"seeds must be 1..20")
        require(type(config.get("full_refit",False)) is bool,"full_refit must be boolean")
        return
    elif task=="forecasting":require(config.get("family","seasonal_naive") in {"seasonal_naive","lag_ridge","lag_boosting"},"Unsupported forecast family")
    else:require(config.get("operator","anneal") in {"greedy","local","anneal","restart","exact"},"Unknown optimization operator")
    params=config.get("parameters") or {}
    require(isinstance(params,dict),"Invalid model parameters")
    for key in ("iterations","max_depth","max_leaf_nodes"):
        if key in params:require(type(params[key]) is int and 1<=params[key]<=max_iterations,"Model iteration/depth bound exceeded")
    require(type(config.get("iterations",100)) is int and 1<=config.get("iterations",100)<=100000,"Search iteration bound exceeded")


def artifacts_complete(manifest, root):
    require(bool(manifest), "Artifact manifest is empty")
    root = Path(root).resolve()
    for relative, expected in manifest.items():
        path = (root / relative).resolve()
        require(path.is_relative_to(root) and path.is_file(), "Artifact missing or outside run directory")
        require(checksum(path) == expected, "Artifact checksum mismatch")


def acceptance(result, metadata, root):
    require(result.get("complete") is True, "Incomplete run")
    require(result.get("evaluator_hash") == metadata["evaluator_hash"], "Evaluator modified")
    require(result.get("config_hash") == fingerprint(metadata["config"]), "Config mismatch")
    require(result.get("data_hash") == metadata["data_hash"] and result.get("split_hash") == metadata["split_hash"], "Incompatible evaluation")
    scores = result.get("fold_scores", [])
    require(bool(scores) and all(type(x) in (int, float) and math.isfinite(x) for x in scores), "Nonfinite/missing scores")
    require(result.get("score_type") in {"base_oof", "exact", "rolling_origin", "conditional_meta_cv", "nested"}, "Invalid score type")
    artifacts_complete(result.get("artifacts"), root)


def paid_launch(*args, **kwargs):
    raise GateError("Paid execution disabled; no isolated credential broker configured")
