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
