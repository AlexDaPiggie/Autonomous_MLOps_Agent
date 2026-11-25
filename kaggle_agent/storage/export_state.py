import json
import uuid
from pathlib import Path
from kaggle_agent.storage.database import utcnow


def atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temp = path.with_suffix(path.suffix + "."+uuid.uuid4().hex+".tmp")
    temp.write_text(content,encoding="utf-8")
    temp.replace(path)


def export_state(store, competition, directory):
    """Generated views stay under .kaggle-agent; never replace human STATE.md."""
    target = Path(directory)/".kaggle-agent"/"views"
    comp = store.rows("SELECT * FROM competitions WHERE id=?", (competition,))[0]
    results = store.rows("SELECT id,state,fidelity,result,failure_reason FROM experiments WHERE competition=? ORDER BY created", (competition,))
    lines = ["# Generated competition state",f"Updated UTC: {utcnow()}",f"State: {comp['state']}",
             f"Standalone champion: {comp['champion']}",f"Ensemble champion: {comp['ensemble_champion']}",
             "Human STATE.md and legacy history remain authoritative for unimported work."]
    atomic_write(target/"STATE.md","\n\n".join(lines)+"\n")
    leaderboard = ["# Generated local leaderboard", "", "| Experiment | State | Fidelity | Fold scores |", "|---|---|---|---|"]
    for row in results:
        result = json.loads(row["result"]) if row["result"] else {}
        leaderboard.append(f"| {row['id']} | {row['state']} | {row['fidelity']} | {result.get('fold_scores', 'unknown')} |")
    atomic_write(target/"local_leaderboard.md","\n".join(leaderboard)+"\n")
    preds = store.rows("SELECT p.* FROM predictions p JOIN experiments e ON e.id=p.experiment WHERE e.competition=?",(competition,))
    atomic_write(target/"prediction_registry.jsonl","".join(json.dumps(row)+"\n" for row in preds))
    try:  # progress page for `ka dash`; never let a display problem break a run
        from kaggle_agent.dashboard import build
        build(store,competition,directory,json.loads(comp["profile"]))
    except Exception:
        pass
    return str(target)
