"""Lease-protected durable controller; launch intents precede external effects."""
import json
from pathlib import Path
import sqlite3
import time
import uuid
from kaggle_agent.execution.gates import prelaunch, acceptance, artifacts_complete, require, validate_profile
from kaggle_agent.storage.database import fingerprint, utcnow
from .lifecycle import transition


class Controller:
    def __init__(self, store, competition):
        self.store, self.competition = store, competition
        self.owner = uuid.uuid4().hex

    def register(self, path, profile):
        digest = validate_profile(profile,check_deadline=False)
        with self.store.transaction() as db:
            row = db.execute("SELECT * FROM competitions WHERE id=?", (self.competition,)).fetchone()
            if row:
                require(row["path"] == str(path), "Competition moved: version/import explicitly before running")
                if row["profile_hash"] != digest:
                    # Identity fields are frozen; notes like deadline or target score may change.
                    old = json.loads(row["profile"])
                    frozen = ("task","metric","direction","data_hash","split_hash","data","validation")
                    require(all(old.get(k) == profile.get(k) for k in frozen), "Profile identity changed (task, metric, data or folds): start a new competition folder")
                    db.execute("UPDATE competitions SET profile=?,profile_hash=? WHERE id=?", (json.dumps(profile), digest, self.competition))
                    self.store.event("profile_updated", {k: profile.get(k) for k in profile if old.get(k) != profile.get(k)}, self.competition, db)
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

    def launch(self, campaign, metadata, provider, *, smoke_passed, seconds=60, memory_mb=512, payload=None, fidelity="full",branch=None,parent=None):
        from kaggle_agent.supervisor.limits import Limits
        limits = Limits(self.store).get()
        with self.store.transaction() as db:
            comp = self.assert_lease(db)
            require(not comp["stop_requested"], "User stop requested")
            profile = json.loads(comp["profile"])
            digest = prelaunch(profile, metadata, smoke_passed=smoke_passed, seconds=seconds, memory_mb=memory_mb, provider=provider.name, limits=limits)
            for source in metadata["config"].get("blend_sources",[]):
                registered=db.execute("SELECT p.*,e.metadata,e.result,e.fidelity FROM predictions p JOIN experiments e ON p.experiment=e.id WHERE p.path=? AND p.checksum=? AND e.competition=? AND e.state='COMPLETED'",(source["path"],source["sha256"],self.competition)).fetchone()
                require(registered is not None and registered["fidelity"]=="full","Blend sources must be full registered predictions")
                source_meta=json.loads(registered["metadata"]);source_result=json.loads(registered["result"])
                require(source_result.get("independently_scored") and source_result["score_type"]=="base_oof","Blend inputs require independently scored base OOF")
                require(all(metadata[k]==source_meta[k] for k in ("data_hash","split_hash","evaluator_hash","metric","dataset_checksum")),"Incompatible blend source provenance")
            camp = db.execute("SELECT * FROM campaigns WHERE id=? AND competition=?", (campaign, self.competition)).fetchone()
            require(camp and (fidelity != "full" or camp["attempts"] < camp["max_trials"]), "Campaign trial cap reached")
            # Screen/intermediate stages count too: at most three launches per trial.
            launches = db.execute("SELECT count(*) FROM experiments WHERE campaign=?", (campaign,)).fetchone()[0]
            require(launches < 3 * camp["max_trials"], "Campaign launch cap reached (3 stages per trial)")
            require(not db.execute("SELECT 1 FROM remote_jobs j JOIN experiments e ON e.id=j.experiment WHERE e.competition=? AND j.state IN ('INTENT','RUNNING','UNKNOWN')", (self.competition,)).fetchone(), "Reconcile active/ambiguous job first")
            key = uuid.uuid4().hex
            if branch:require(db.execute("SELECT id FROM research_branches WHERE id=? AND competition=?",(branch,self.competition)).fetchone(),"Branch belongs to different competition")
            if parent:require(db.execute("SELECT id FROM experiments WHERE id=? AND competition=?",(parent,self.competition)).fetchone(),"Parent belongs to different competition")
            db.execute("INSERT INTO experiments(id,competition,campaign,branch,parent,fingerprint,state,fidelity,metadata,created) VALUES(?,?,?,?,?,?,?,?,?,?)",
                       (key, self.competition, campaign, branch, parent, digest, "RUNNING", fidelity, json.dumps(metadata), utcnow()))
            db.execute("INSERT INTO remote_jobs(key,experiment,provider,state,heartbeat,details) VALUES(?,?,?,?,?,?)", (key,key,provider.name,"INTENT",utcnow(),json.dumps(dict(seconds=seconds,memory_mb=memory_mb))))
            db.execute("UPDATE campaigns SET attempts=attempts+?,state='RUNNING' WHERE id=?", (int(fidelity=="full"),campaign))
            if comp["state"] != "PENDING":
                transition(self.store,self.competition,"PENDING","next bounded experiment",db)
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

    def recover_interrupted(self, provider):
        """After Ctrl+C, a crash or a failed finish: settle leftovers so `ka go` can resume.

        Jobs that really ended are reconciled first. An experiment still marked RUNNING
        whose job is not active any more never got scored, so it is marked FAILED
        (the code can run again). Then a mid-run competition state becomes STOPPED,
        from which a new campaign may start.
        """
        self.reconcile(provider)
        with self.store.transaction() as db:
            comp = self.assert_lease(db)
            if db.execute("SELECT 1 FROM remote_jobs j JOIN experiments e ON e.id=j.experiment WHERE e.competition=? AND j.state IN ('INTENT','RUNNING','UNKNOWN')", (self.competition,)).fetchone():
                return False   # a job is still alive: campaign() reports it
            stale = db.execute("UPDATE experiments SET state='FAILED',failure_reason=COALESCE(failure_reason,'interrupted before scoring') WHERE competition=? AND state='RUNNING'", (self.competition,)).rowcount
            if comp["state"] in {"IMPLEMENTING", "TESTING", "RUNNING", "EVALUATING"}:
                transition(self.store, self.competition, "STOPPED", "interrupted run recovered", db)
                self.store.event("interrupted_recovered", dict(experiments=stale), self.competition, db)
            return True

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
                details=json.loads(job["details"]);details["last_provider_status"]=result
                db.execute("UPDATE remote_jobs SET details=? WHERE key=?",(json.dumps(details),job["key"]))
                if state == "UNKNOWN":
                    transition(self.store,self.competition,"BLOCKED","ambiguous launch; never duplicate",db)
                elif state in {"RUNNING","COMPLETED"}:
                    comp=db.execute("SELECT state FROM competitions WHERE id=?",(self.competition,)).fetchone()
                    if comp[0]=="BLOCKED":
                        transition(self.store,self.competition,"PENDING","job reconciled",db)
                        transition(self.store,self.competition,"TESTING","recovered persisted checks",db)
                        transition(self.store,self.competition,"RUNNING","original job recovered",db)
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
            metadata=json.loads(exp["metadata"])
            if metadata["config"].get("script_sha256") and (Path(root)/"code").is_dir():
                from kaggle_agent.execution.script import code_hash
                require(code_hash(Path(root)/"code")==metadata["config"]["script_sha256"],"Script changed after launch")
            if "data_spec" in metadata:
                from kaggle_agent.evaluation.validation import independently_score
                from kaggle_agent.execution.identity import code_version
                require(metadata["code_hash"]==code_version(),"Experiment code changed after launch")
                scores=independently_score(metadata,root)
                require(len(scores)==len(result["fold_scores"]) and all(abs(a-b)<1e-9 for a,b in zip(scores,result["fold_scores"])),"Reported metric differs from independent evaluator")
                result=result|dict(fold_scores=scores,independently_scored=True)
            elif "dataset_path" in metadata:
                from kaggle_agent.evaluation.validation import independently_score
                from kaggle_agent.execution.identity import code_version
                require(metadata["code_hash"]==code_version(),"Experiment code changed after launch")
                scores=independently_score(metadata,root)
                require(len(scores)==len(result["fold_scores"]) and all(abs(a-b)<1e-10 for a,b in zip(scores,result["fold_scores"])),"Reported metric differs from independent evaluator")
                result=result|dict(fold_scores=scores,independently_scored=True)
                if metadata["config"].get("blend_sources"):
                    artifact=json.loads((Path(root)/"predictions.json").read_text())
                    require(result.get("ensemble_baseline_scores")==artifact["ensemble_baseline_scores"],"Baseline meta-score mismatch")
            require(not self.should_stop(), "Stopped results require explicit recovery review")
            transition(self.store,self.competition,"EVALUATING","independent artifact checks",db)
            db.execute("UPDATE experiments SET state='COMPLETED',result=? WHERE id=?", (json.dumps(result,allow_nan=False),experiment))
            from kaggle_agent.storage.database import checksum
            for relative,digest in result["artifacts"].items():
                path=str((Path(root)/relative).resolve())
                db.execute("INSERT INTO predictions VALUES(?,?,?,?,?)",(fingerprint(dict(experiment=experiment,path=path)),experiment,path,digest,json.dumps(metadata)))
            logs={str(p.resolve()):checksum(p) for p in Path(root).glob("*.log")}
            self.store.event("experiment_completed",dict(experiment=experiment,logs=logs,stdout_stderr="combined worker.log",
                             next_action="assess champions and portfolio"),self.competition,db)
            db.execute("UPDATE remote_jobs SET state='COMPLETED' WHERE experiment=?", (experiment,))
            db.execute("UPDATE campaigns SET state='COMPLETED',next_action='review portfolio' WHERE id=?", (exp["campaign"],))
            transition(self.store,self.competition,"COMPLETED","campaign completed; system may continue",db)

    def record(self, metadata, result, root, *, fidelity="full", branch=None, parent=None, source="manual"):
        """Register a run that happened outside the supervisor (manual or Modal).

        The scores in `result` are ignored: they are recomputed here from the
        frozen data and the copied artifacts, exactly as for supervised runs.
        """
        from kaggle_agent.evaluation.validation import independently_score
        from kaggle_agent.execution.gates import experiment_fingerprint
        require(fidelity in {"screen","intermediate","full"},"Unknown fidelity")
        with self.store.transaction() as db:
            comp=self.assert_lease(db)
            profile=json.loads(comp["profile"])
            require(metadata["data_hash"]==profile["data_hash"] and metadata["split_hash"]==profile["split_hash"],"Data/split mismatch: files changed since the profile was frozen")
            require(metadata["metric"]==profile["metric"],"Metric mismatch")
            if branch:require(db.execute("SELECT id FROM research_branches WHERE id=? AND competition=?",(branch,self.competition)).fetchone(),"Unknown branch")
            if parent:require(db.execute("SELECT id FROM experiments WHERE id=? AND competition=?",(parent,self.competition)).fetchone(),"Unknown parent")
            artifacts_complete(result["artifacts"],root)
            scores=independently_score(metadata,root)
            result=result|dict(fold_scores=scores,independently_scored=True,source=source)
            key=Path(root).name
            try:
                db.execute("INSERT INTO experiments(id,competition,campaign,branch,parent,fingerprint,state,fidelity,metadata,result,created) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                           (key,self.competition,None,branch,parent,experiment_fingerprint(metadata),"COMPLETED",fidelity,json.dumps(metadata),json.dumps(result,allow_nan=False),utcnow()))
            except sqlite3.IntegrityError:
                require(False,"Duplicate run: same code, config, data, folds and seed already registered")
            for relative,digest in result["artifacts"].items():
                path=str((Path(root)/relative).resolve())
                db.execute("INSERT INTO predictions VALUES(?,?,?,?,?)",(fingerprint(dict(experiment=key,path=path)),key,path,digest,json.dumps(metadata)))
            self.store.event("experiment_registered",dict(experiment=key,source=source,fidelity=fidelity,fold_scores=scores),self.competition,db)
        return key,result
