"""Small heuristic portfolio. No LLM calls per trial or hidden search tree."""
from datetime import datetime, timezone
import json
import math
import uuid
from kaggle_agent.execution.gates import require
from kaggle_agent.storage.database import utcnow


class Portfolio:
    def __init__(self, store, competition):
        self.store,self.competition = store,competition

    def add(self, name, hypothesis, *, expected_gain=0., uncertainty=1., novelty=1., cost_cents=0, feasibility=1., source=None):
        require(bool(hypothesis),"Hypothesis required")
        values = [expected_gain,uncertainty,novelty,cost_cents,feasibility]
        require(all(math.isfinite(v) and v >= 0 for v in values),"Invalid branch estimates")
        key = uuid.uuid4().hex
        details = dict(hypothesis=hypothesis,expected_gain=expected_gain,uncertainty=uncertainty,
                       novelty=novelty,cost_cents=cost_cents,feasibility=feasibility,source=source,
                       standalone_gain=0.,ensemble_gain=0.,spent_cents=0,failures=0,trials=0)
        with self.store.transaction() as db:
            count = db.execute("SELECT count(*) FROM research_branches WHERE competition=? AND status='active'",(self.competition,)).fetchone()[0]
            require(count < 5,"At most five active directions; park one first")
            db.execute("INSERT INTO research_branches VALUES(?,?,?,?,?,?)",(key,self.competition,name,"active",json.dumps(details),utcnow()))
        return key

    def update(self, key, *, status=None, standalone_gain=0., ensemble_gain=0., cost_cents=0, execution_failed=False):
        require(status is None or status in {"active","parked","exhausted"},"Invalid branch status")
        require(type(cost_cents) is int and cost_cents >= 0,"Invalid branch cost")
        with self.store.transaction() as db:
            row = db.execute("SELECT * FROM research_branches WHERE id=? AND competition=?",(key,self.competition)).fetchone()
            require(row is not None,"Unknown branch")
            if status == "active" and row["status"] != "active":
                require(db.execute("SELECT count(*) FROM research_branches WHERE competition=? AND status='active'",(self.competition,)).fetchone()[0] < 5,"Active branch cap")
            details = json.loads(row["details"])
            details["spent_cents"] += cost_cents
            details["failures"] += int(execution_failed)
            details["trials"] += int(not execution_failed)
            details["standalone_gain"] = max(details["standalone_gain"],standalone_gain)
            details["ensemble_gain"] = max(details["ensemble_gain"],ensemble_gain)
            db.execute("UPDATE research_branches SET status=?,details=?,updated=? WHERE id=?",(status or row["status"],json.dumps(details,allow_nan=False),utcnow(),key))

    def rank(self, turn=0):
        rows = self.store.rows("SELECT * FROM research_branches WHERE competition=? AND status!='exhausted'",(self.competition,))
        now = datetime.now(timezone.utc)
        for row in rows:
            d = json.loads(row["details"])
            age = (now-datetime.fromisoformat(row["updated"])).total_seconds()/86400
            row["priority"] = d["feasibility"] * (d["expected_gain"] + .25*d["uncertainty"] + .1*d["novelty"]) / (1+d["cost_cents"]) / (1+d["failures"]) + min(age,30)*.001
            row["details"] = d
        if turn % 4 == 3:  # explicit 25% exploration quota, including parked directions
            return sorted(rows,key=lambda r:(r["details"]["trials"],r["updated"]))
        return sorted(rows,key=lambda r:r["priority"],reverse=True)


def stagnation(results, branches=()):
    """Execution failures don't increment the eight completed own-pipeline counter."""
    count = 0
    for row in reversed(results):
        if row.get("state") != "COMPLETED" or row.get("public_merge",False):
            continue
        if row.get("standalone_improved") or row.get("ensemble_improved"):
            break
        count += 1
    return dict(completed_without_progress=count,research_review=count>=8,
                strategic_review=bool(branches) and all(b["status"]=="exhausted" for b in branches),
                next_action="audit validation, weak segments, sources and complementary directions" if count>=8 else "bounded campaign")
