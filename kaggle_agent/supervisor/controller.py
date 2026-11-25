"""Lease-protected durable controller; launch intents precede external effects."""
import json
import time
import uuid
from kaggle_agent.execution.gates import prelaunch, acceptance, require, validate_profile
from kaggle_agent.storage.database import fingerprint, utcnow
from .lifecycle import transition


class Controller:
    def __init__(self, store, competition):
        self.store, self.competition = store, competition
        self.owner = uuid.uuid4().hex

    def register(self, path, profile):
        digest = validate_profile(profile)
        with self.store.transaction() as db:
            row = db.execute("SELECT * FROM competitions WHERE id=?", (self.competition,)).fetchone()
            if row:
                require(row["profile_hash"] == digest and row["path"] == str(path), "Profile changed: version/import explicitly before running")
            else:
                db.execute("INSERT INTO competitions(id,path,profile,profile_hash) VALUES(?,?,?,?)",
                           (self.competition, str(path), json.dumps(profile), digest))

    def acquire(self, ttl=30):
        with self.store.transaction() as db:
            cursor = db.execute("UPDATE competitions SET lease_owner=?,lease_until=?,heartbeat=? WHERE id=? AND (lease_owner=? OR lease_until IS NULL OR lease_until<?)",
                                (self.owner, time.time()+ttl, utcnow(), self.competition, self.owner, time.time()))
            require(cursor.rowcount == 1, "Supervisor lease held by another process")

    def heartbeat(self, **process):
        with self.store.transaction() as db:
            self.assert_lease(db)
            db.execute("UPDATE competitions SET lease_until=?,heartbeat=? WHERE id=?", (time.time()+30, utcnow(), self.competition))
            if process:
                db.execute("UPDATE remote_jobs SET pid=?,process_created=?,heartbeat=? WHERE experiment IN (SELECT id FROM experiments WHERE competition=? AND state='RUNNING')",
                           (process["pid"], process["process_created"], utcnow(), self.competition))

    def assert_lease(self, db):
        row = db.execute("SELECT * FROM competitions WHERE id=?", (self.competition,)).fetchone()
        require(row and row["lease_owner"] == self.owner and row["lease_until"] > time.time(), "Supervisor lease lost")
        return row

    def release(self):
        with self.store.transaction() as db:
            db.execute("UPDATE competitions SET lease_owner=NULL,lease_until=NULL WHERE id=? AND lease_owner=?", (self.competition, self.owner))

    def request_stop(self):
        with self.store.transaction() as db:
            db.execute("UPDATE competitions SET stop_requested=1 WHERE id=?", (self.competition,))
            self.store.event("user_stop", {}, self.competition, db)

    def should_stop(self):
        return bool(self.store.rows("SELECT stop_requested FROM competitions WHERE id=?", (self.competition,))[0]["stop_requested"])

    def campaign(self, max_trials=4, resume=False):
        require(1 <= max_trials <= 4, "Campaigns require 1..4 trials")
        with self.store.transaction() as db:
            row = self.assert_lease(db)
            require(not row["stop_requested"] or resume, "Explicit resume required after user stop")
            require(not db.execute("SELECT 1 FROM remote_jobs j JOIN experiments e ON e.id=j.experiment WHERE e.competition=? AND j.state IN ('INTENT','RUNNING','UNKNOWN')", (self.competition,)).fetchone(), "Reconcile outstanding jobs before campaign")
            if row["state"] != "PENDING":
                transition(self.store, self.competition, "PENDING", "new bounded campaign", db)
            db.execute("UPDATE competitions SET stop_requested=0 WHERE id=?", (self.competition,))
            key = uuid.uuid4().hex
            db.execute("INSERT INTO campaigns(id,competition,state,created,max_trials) VALUES(?,?,?,?,?)", (key, self.competition, "PENDING", utcnow(), max_trials))
            return key

    def launch(self, campaign, metadata, provider, *, smoke_passed, seconds=60, memory_mb=512, payload=None, fidelity="full"):
        with self.store.transaction() as db:
            comp = self.assert_lease(db)
            require(not comp["stop_requested"], "User stop requested")
            profile = json.loads(comp["profile"])
            digest = prelaunch(profile, metadata, smoke_passed=smoke_passed, seconds=seconds, memory_mb=memory_mb, provider=provider.name)
            camp = db.execute("SELECT * FROM campaigns WHERE id=? AND competition=?", (campaign, self.competition)).fetchone()
            require(camp and camp["attempts"] < camp["max_trials"], "Campaign trial cap reached")
            require(not db.execute("SELECT 1 FROM remote_jobs j JOIN experiments e ON e.id=j.experiment WHERE e.competition=? AND j.state IN ('INTENT','RUNNING','UNKNOWN')", (self.competition,)).fetchone(), "Reconcile active/ambiguous job first")
            key = uuid.uuid4().hex
            db.execute("INSERT INTO experiments(id,competition,campaign,fingerprint,state,fidelity,metadata,created) VALUES(?,?,?,?,?,?,?,?)",
                       (key, self.competition, campaign, digest, "RUNNING", fidelity, json.dumps(metadata), utcnow()))
            db.execute("INSERT INTO remote_jobs(key,experiment,provider,state,heartbeat,details) VALUES(?,?,?,?,?,?)", (key,key,provider.name,"INTENT",utcnow(),json.dumps(dict(seconds=seconds,memory_mb=memory_mb))))
            db.execute("UPDATE campaigns SET attempts=attempts+1,state='RUNNING' WHERE id=?", (campaign,))
            transition(self.store,self.competition,"TESTING","smoke passed",db)
            transition(self.store,self.competition,"RUNNING","launch intent persisted",db)
        try:
            job_id = provider.launch(key, payload or {})
        except Exception as error:
            self.store.event("launch_uncertain", {"key":key,"error_type":type(error).__name__}, self.competition)
            self.reconcile(provider)
            return key
        with self.store.transaction() as db:
            db.execute("UPDATE remote_jobs SET job_id=?,state='RUNNING' WHERE key=?", (job_id,key))
        return key

    def reconcile(self, provider):
        jobs = self.store.rows("SELECT j.* FROM remote_jobs j JOIN experiments e ON j.experiment=e.id WHERE e.competition=? AND j.state IN ('INTENT','RUNNING','UNKNOWN')", (self.competition,))
        for job in jobs:
            require(job["provider"] == provider.name, "Use original provider for reconciliation")
            try:
                result = provider.reconcile(job["key"])
            except Exception:
                result = dict(state="UNKNOWN")
            state = result.get("state", "UNKNOWN")
            require(state in {"RUNNING","COMPLETED","FAILED","STOPPED","UNKNOWN"}, "Invalid provider status")
            with self.store.transaction() as db:
                self.assert_lease(db)
                db.execute("UPDATE remote_jobs SET state=?,job_id=COALESCE(?,job_id),heartbeat=? WHERE key=?", (state,result.get("job_id"),utcnow(),job["key"]))
                if state == "UNKNOWN":
                    transition(self.store,self.competition,"BLOCKED","ambiguous launch; never duplicate",db)
                elif state in {"FAILED","STOPPED"}:
                    db.execute("UPDATE experiments SET state=?,failure_reason=? WHERE id=?", (state,"provider terminal",job["experiment"]))
                    transition(self.store,self.competition,state,"provider terminal",db)
                self.store.event("job_reconciled",dict(key=job["key"],state=state),self.competition,db)
        return jobs

    def finish(self, experiment, result, root):
        with self.store.transaction() as db:
            self.assert_lease(db)
            exp = db.execute("SELECT * FROM experiments WHERE id=? AND competition=?", (experiment,self.competition)).fetchone()
            require(exp and exp["state"] == "RUNNING", "Experiment not active")
            acceptance(result,json.loads(exp["metadata"]),root)
            require(not self.should_stop(), "Stopped results require explicit recovery review")
            transition(self.store,self.competition,"EVALUATING","independent artifact checks",db)
            db.execute("UPDATE experiments SET state='COMPLETED',result=? WHERE id=?", (json.dumps(result,allow_nan=False),experiment))
            db.execute("UPDATE remote_jobs SET state='COMPLETED' WHERE experiment=?", (experiment,))
            db.execute("UPDATE campaigns SET state='COMPLETED',next_action='review portfolio' WHERE id=?", (exp["campaign"],))
            transition(self.store,self.competition,"COMPLETED","campaign completed; system may continue",db)
