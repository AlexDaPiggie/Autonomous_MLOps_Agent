"""Bounded local evidence review; no causal claims or automatic notebook execution."""
import json
from pathlib import Path
from kaggle_agent.storage.export_state import atomic_write
from .retrieval import Knowledge


def review_stagnation(store,competition,directory,profile):
    comp=store.rows("SELECT * FROM competitions WHERE id=?",(competition,))[0]
    branches=store.rows("SELECT id,name,status,details FROM research_branches WHERE competition=?",(competition,))
    recent=store.rows("SELECT id,state,result,failure_reason FROM experiments WHERE competition=? ORDER BY created DESC LIMIT 8",(competition,))
    scores=[dict(experiment=r["id"],fold_scores=json.loads(r["result"])["fold_scores"]) for r in recent if r["result"]]
    findings=dict(trigger="eight completed own-pipeline trials without validated progress",champion=comp["champion"],
                  fold_diagnostics=scores,branches=branches,
                  relevant_evidence=Knowledge(store).search(profile["task"]+" "+profile["metric"],domain=profile["task"],external_allowed=False),
                  checks=["Recheck frozen split/evaluator identities and full artifact integrity", "Inspect weak folds/segments before a causal explanation"],
                  reframes=["Change representation with train/inference parity checks", "Test a complementary model using conditional meta-validation", "Revisit parked hypotheses with changed assumptions"],
                  next_action="Review local evidence and provide one changed configuration/hypothesis for the next bounded campaign",
                  causal_explanation="unknown")
    path=Path(directory)/".kaggle-agent"/"research-review.json"
    atomic_write(path,json.dumps(findings,indent=2))
    store.event("research_review",dict(path=str(path),champion=comp["champion"]),competition)
    return findings
