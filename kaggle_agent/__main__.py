"""Local CLI. Execution is explicit, remote backends are unavailable."""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

from kaggle_agent.agents.base import CLIAdapter,MockAgent
from kaggle_agent.agents.session_manager import checkpoint,rotate
from kaggle_agent.execution.gates import GateError,require,validate_profile
from kaggle_agent.storage.database import Store,checksum,fingerprint
from kaggle_agent.storage.export_state import atomic_write,export_state
from kaggle_agent.storage.migration import migrate,LEGACY
from kaggle_agent.supervisor.budget import Budget
from kaggle_agent.supervisor.controller import Controller
from kaggle_agent.supervisor.lifecycle import transition


def home():
    return Path(os.environ.get("KAGGLE_AGENT_HOME",str(Path.home()/".kaggle-agent"))).resolve()


def competition_id(directory):return fingerprint(str(Path(directory).resolve()).casefold())[:20]


def init_real(root,task,args):
    """Profile for a real competition: CSV/Parquet tables with frozen folds, or an
    optimization scorer plugin. rules_reviewed stays false until you check the rules."""
    from kaggle_agent import data as tables
    from kaggle_agent.evaluation.validation import direction
    from kaggle_agent.pipelines import plugin
    folder=root/".kaggle-agent";profile_path=folder/"profile.json"
    if task=="optimization":
        require(bool(args.scorer) and bool(args.solution_name),"Optimization needs --scorer and --solution-name")
        scorer=Path(args.scorer).resolve()
        require(scorer.is_file(),"Scorer file not found")
        target=folder/"scorer.py"
        if scorer!=target.resolve():
            folder.mkdir(parents=True,exist_ok=True);shutil.copyfile(scorer,target)
        spec=dict(kind="optimization",scorer=".kaggle-agent/scorer.py",files=[f for f in (args.files or "").split(",") if f],solution_name=args.solution_name)
        ident=plugin.identity(root,spec)
        metric,way=args.metric or "objective",args.direction or "minimize"
        validation="exact scorer plugin"
    else:
        require(bool(args.train) and bool(args.test) and bool(args.target),"Tables need --train, --test and --target (and --id)")
        rel=lambda p:os.path.relpath(Path(p).resolve(),root).replace("\\","/")
        spec=dict(kind="tables",train=rel(args.train),test=rel(args.test),id_column=args.id,target_column=args.target,folds=".kaggle-agent/folds.csv")
        if task=="classification":spec["classes"]=tables.class_order(root,spec)
        if not (root/spec["folds"]).exists():
            spec["fold_scheme"]=tables.make_folds_file(root,spec,task="classification" if task=="classification" else "regression",
                                                       n_splits=args.folds,seed=args.seed,group_column=args.group,time_column=args.time)
        else:spec["fold_scheme"]="time" if args.time else "group" if args.group else "kfold"
        ident=tables.identity(root,spec)
        metric=args.metric or ("log_loss" if task=="classification" else "rmse")
        way=args.direction or direction(metric)
        validation={"time":"expanding-window time folds","group":"group k-fold"}.get(spec["fold_scheme"],"stratified k-fold" if task=="classification" else "k-fold")
    profile=dict(task="classification" if task=="classification" else "regression" if task in {"regression","forecasting"} else "optimization",
                 metric=metric,direction=way,data=spec,rules_reviewed=False,external_resources=[],validation=validation,
                 deadline=None,baseline=None,constraints={},version=1,synthetic=False,target_score=None,
                 legacy_limits_reviewed=not any((root/name).exists() for name in ("CONFIG.md","STATE.md")),**ident)
    atomic_write(profile_path,json.dumps(profile,indent=2))
    return dict(profile=str(profile_path),folds=spec.get("folds"),dry_run=True,
                next_action="Read the competition rules, then set rules_reviewed=true (and deadline/target_score if known) in profile.json")


def init(directory,task,demo=False,args=None):
    root=Path(directory).resolve()
    require(root.is_dir(),"Competition directory must exist")
    folder=root/".kaggle-agent";profile_path=folder/"profile.json"
    require(not profile_path.exists(),"Profile already exists; inspect/version it explicitly")
    if args is not None and not demo and (getattr(args,"train",None) or getattr(args,"scorer",None)):
        return init_real(root,task,args)
    profile=dict(task=task,metric="log_loss" if task=="classification" else "objective" if task=="optimization" else "rmse",
                 direction="maximize" if task=="optimization" else "minimize",data_hash="",split_hash="",rules_reviewed=False,
                 external_resources=[],validation="fixed CV" if task in {"classification","regression"} else "exact" if task=="optimization" else "rolling_origin",
                 deadline=None,baseline=None,constraints={},version=1,synthetic=demo)
    profile["legacy_limits_reviewed"]=not any((root/name).exists() for name in ("CONFIG.md","STATE.md"))
    if demo:
        from kaggle_agent.benchmarks import synthetic
        data=synthetic(task)
        atomic_write(folder/"dataset.json",json.dumps(data,allow_nan=False))
        profile.update(rules_reviewed=True,**dataset_identity(data))
    atomic_write(profile_path,json.dumps(profile,indent=2))
    return dict(profile=str(profile_path),dry_run=True,next_action="Review profile and frozen dataset; start defaults to dry-run")


def dataset_identity(data):
    if data["task"] in {"classification","regression"}:
        return dict(data_hash=fingerprint(data),split_hash=fingerprint(dict(ids=data["ids"],folds=data["folds"])))
    return dict(data_hash=fingerprint(data),split_hash=fingerprint({k:data[k] for k in ("origins","horizon","times") if k in data} or dict(exact=True)))


def load_competition(args,store):
    directory=Path(args.competition).resolve()
    path=directory/".kaggle-agent"/"profile.json"
    require(path.is_file(),"Run init first, then review profile and dataset")
    profile=json.loads(path.read_text(encoding="utf-8"))
    validate_profile(profile,check_deadline=False)
    controller=Controller(store,competition_id(directory));controller.register(directory,profile)
    return directory,profile,controller


def run(args,store):
    from kaggle_agent import runs
    from kaggle_agent.supervisor.limits import Limits,run_bounds
    directory,profile,controller=load_competition(args,store)
    real=runs.is_real(profile)
    dataset=directory/".kaggle-agent"/"dataset.json"
    if real:
        require(runs.identity(directory,profile)=={k:profile[k] for k in ("data_hash","split_hash")},"Data, folds or scorer changed since the profile was frozen")
        data=None
    else:
        require(dataset.is_file(),"Frozen dataset.json required (or init with --train/--test); see operating guide")
        data=json.loads(dataset.read_text(encoding="utf-8"))
        require(dataset_identity(data)=={k:profile[k] for k in ("data_hash","split_hash")},"Dataset/split profile mismatch")
        require(data["task"]==profile["task"],"Dataset task mismatch")
    require(profile.get("legacy_limits_reviewed",False),"Review legacy CONFIG/STATE limits and active jobs before setting legacy_limits_reviewed=true")
    limits=Limits(store).get();bounds=run_bounds(limits,profile)
    if args.seconds is None:args.seconds=bounds["seconds"]
    if args.memory_mb is None:args.memory_mb=min(1024,bounds["memory_mb"]) if not real else bounds["memory_mb"]
    require(0<args.seconds<=bounds["seconds"] and 0<args.memory_mb<=bounds["memory_mb"],"Resource bounds exceed configured limits/profile caps (see: limits)")
    require(1<=args.campaigns<=20 and 1<=args.trials<=4,"Bound campaigns to 1..20 and trials to 1..4")
    config=json.loads(Path(args.config).read_text()) if args.config else dict(seed=42,metric=profile["metric"])
    require(config.get("metric")==profile["metric"],"Config metric mismatch")
    mode=getattr(args,"mode","propose")
    require(mode=="propose" or real,"Code mode needs a real data profile (init with --train/--test, or --scorer)")
    require(mode=="code" or not real or profile["data"]["kind"]=="tables","Optimization plugin competitions use --mode code (the agent writes the solver)")
    if not args.execute:
        return dict(dry_run=True,agent=args.agent,mode=mode,campaigns=args.campaigns,trials=args.trials,config=config,
                    limits=bounds,paid_execution=False,submissions=False,next_action="Use --execute for bounded local CPU execution")
    require(args.agent=="mock" or args.subscription_confirmed,"Confirm installed CLI uses selected subscription before agent execution")
    if args.agent!="mock":require(Budget(store).summary()["config"]["confirmed"],"Confirm fixed subscription expenses and billing period in global budget first")
    if mode=="code":
        from kaggle_agent.loop import run_code_campaigns
        require(args.agent!="mock" or getattr(args,"mock_agent",None) is not None,"Code mode needs --agent claude or codex")
        agent=getattr(args,"mock_agent",None) or CLIAdapter(args.agent)
        controller.acquire()
        try:
            outstanding=store.rows("SELECT j.* FROM remote_jobs j JOIN experiments e ON e.id=j.experiment WHERE e.competition=? AND j.state IN ('INTENT','RUNNING','UNKNOWN')",(controller.competition,))
            if outstanding:
                from kaggle_agent.execution.script import ScriptProvider
                controller.reconcile(ScriptProvider(directory/".kaggle-agent"/"jobs"))
                still=store.rows("SELECT j.* FROM remote_jobs j JOIN experiments e ON e.id=j.experiment WHERE e.competition=? AND j.state IN ('INTENT','RUNNING','UNKNOWN')",(controller.competition,))
                require(not still,"A previous run is still active or ambiguous; check status before resuming")
            return run_code_campaigns(args,store,directory,profile,controller,agent,on_event=getattr(args,"on_event",None))
        except KeyboardInterrupt:
            controller.request_stop();transition(store,controller.competition,"STOPPED","keyboard interrupt")
            return dict(state="STOPPED")
        except (ValueError,OSError,RuntimeError) as error:
            transition(store,controller.competition,"STOPPED" if "deadline" in str(error).lower() else "BLOCKED",str(error))
            raise
        finally:
            from kaggle_agent.agents.session_manager import checkpoint as save_checkpoint
            save_checkpoint(store,controller.competition,"inspect status and resume",directory/".kaggle-agent"/"checkpoint.json")
            export_state(store,controller.competition,directory)
            controller.release()
    from kaggle_agent.execution.local import LocalProvider
    from kaggle_agent.execution.identity import code_version
    from kaggle_agent.evaluation.validation import evaluator_version,promote
    from kaggle_agent.research.branches import Portfolio,stagnation
    controller.acquire()
    jobs=directory/".kaggle-agent"/"jobs"
    provider=LocalProvider(jobs,seconds=args.seconds,memory_mb=args.memory_mb,threads=bounds["threads"],heartbeat=controller.heartbeat,should_stop=controller.should_stop)
    completed=[]
    try:
        outstanding=store.rows("SELECT j.* FROM remote_jobs j JOIN experiments e ON e.id=j.experiment WHERE e.competition=? AND j.state IN ('INTENT','RUNNING','UNKNOWN','COMPLETED') AND e.state='RUNNING'",(controller.competition,))
        if outstanding:
            controller.reconcile(provider)
            for job in outstanding:
                state=provider.reconcile(job["key"])
                if state["state"]=="COMPLETED":
                    result=json.loads((jobs/job["key"]/"result.json").read_text())
                    controller.finish(job["experiment"],result,jobs/job["key"])
                    completed.append(job["experiment"])
                elif state["state"]=="RUNNING":
                    return dict(state="RUNNING",next_action="Existing process alive; resume later, no duplicate launch",job=job["key"])
                elif state["state"]=="UNKNOWN":
                    return dict(state="BLOCKED",next_action="Reconcile ambiguous job manually; no relaunch")
        if not store.rows("SELECT id FROM research_branches WHERE competition=?",(controller.competition,)):
            portfolio=Portfolio(store,controller.competition)
            for name,hypothesis in (("baseline","Validate simple inductive bias"),("representation","Test interactions/lag representation"),("diversity","Evaluate complementary family")):
                portfolio.add(name,hypothesis)
        for campaign_index in range(args.campaigns):
            if controller.should_stop() and not args.command=="resume":break
            validate_profile(profile)  # deadline checked at every campaign
            campaign=controller.campaign(args.trials,resume=args.command=="resume")
            cp=checkpoint(store,controller.competition,"bounded campaign",directory/".kaggle-agent"/"checkpoint.json")
            agent=MockAgent() if args.agent=="mock" else CLIAdapter(args.agent)
            agent_result=agent.resume("Review next bounded research task; report protocol JSON. No remote actions. You may propose up to four hypothesis/config objects in proposals, using only documented local model families/configs. Propose a distinct useful change, not a repeated equivalent trial.",directory,cp,
                                      authorized=True,seconds=min(args.seconds,300),heartbeat=controller.heartbeat,should_stop=controller.should_stop)
            session=rotate(store,controller.competition,args.agent,cp)
            with store.transaction() as db:
                db.execute("UPDATE agent_sessions SET state=?,result=? WHERE id=?",(agent_result.status,json.dumps(asdict(agent_result)),session))
            if agent_result.status!="completed":
                target={"waiting_limit":"WAITING_LIMIT","stopped":"STOPPED","failed":"FAILED"}.get(agent_result.status,"BLOCKED")
                transition(store,controller.competition,target,agent_result.termination_reason)
                break
            for trial in range(args.trials):
                if controller.should_stop():break
                validate_profile(profile)
                trial_config=config.copy()
                if agent_result.proposals and trial<len(agent_result.proposals):
                    proposal=agent_result.proposals[trial]
                    trial_config=proposal["config"]|dict(metric=profile["metric"])
                elif args.trials>1:
                    if profile["task"] in {"classification","regression"}:trial_config["family"]=("linear","forest","hist","linear")[trial]
                    elif profile["task"]=="optimization":trial_config["operator"]=("greedy","local","anneal","restart")[trial]
                    else:trial_config["family"]=("seasonal_naive","lag_ridge","lag_boosting","seasonal_naive")[trial]
                    trial_config["seed"]=config.get("seed",42)+campaign_index*4+trial
                from kaggle_agent.execution.gates import validate_config
                validate_config(profile["task"],trial_config,max_iterations=limits["max_iterations"])
                require(not trial_config.get("blend_sources"),"Use supervised registered-library assessment for blends")
                # Use a tiny synthetic instance through exactly the selected runner.
                from kaggle_agent.benchmarks import synthetic
                smoke_data=synthetic(profile["task"],0)
                smoke_dataset=directory/".kaggle-agent"/"smoke-dataset.json"
                atomic_write(smoke_dataset,json.dumps(smoke_data))
                smoke_key="smoke-"+fingerprint(dict(config=trial_config,code=code_version()))[:20]
                smoke_plan=dict(dataset=str(smoke_dataset),config=trial_config,evaluator_hash=evaluator_version(),**dataset_identity(smoke_data))
                smoke_provider=LocalProvider(directory/".kaggle-agent"/"smoke",seconds=min(args.seconds,60),memory_mb=args.memory_mb,heartbeat=controller.heartbeat,should_stop=controller.should_stop)
                if not (smoke_provider.directory/smoke_key).exists():smoke_provider.launch(smoke_key,smoke_plan)
                smoke_passed=smoke_provider.reconcile(smoke_key)["state"]=="COMPLETED"
                require(smoke_passed,"Selected model failed bounded synthetic real-path smoke; inspect smoke log")
                if real:
                    metadata=runs.metadata(directory,profile,trial_config,hypothesis=agent_result.proposals[trial]["hypothesis"] if agent_result.proposals and trial<len(agent_result.proposals) else "bounded local baseline/portfolio trial")
                    metadata["code_revision"]=git_revision()
                else:
                    metadata=dict(code_hash=code_version(),config=trial_config,seed=trial_config.get("seed",42),metric=profile["metric"],
                                  evaluator_hash=evaluator_version(),dataset_path=str(dataset),dataset_checksum=checksum(dataset),
                                  **dataset_identity(data),hypothesis="bounded local baseline/portfolio trial",code_revision=git_revision())
                portfolio=Portfolio(store,controller.competition)
                ranked=portfolio.rank(turn=campaign_index*args.trials+trial)
                branch=ranked[0]["id"] if ranked else None
                key=None;parent=None;duplicate=False
                for fidelity in ("screen","intermediate","full"):
                    stage_config=trial_config|dict(_fidelity=fidelity)
                    if fidelity!="full":
                        family=stage_config.get("family","linear")
                        if profile["task"] in {"classification","regression"}:
                            from kaggle_agent.pipelines.tabular import FAMILY_PARAMETERS
                            if "iterations" in FAMILY_PARAMETERS.get(family,()):
                                stage_config["parameters"]=(stage_config.get("parameters") or {})|dict(iterations=2 if fidelity=="screen" else 10)
                        elif profile["task"]=="forecasting":
                            stage_config["parameters"]=(stage_config.get("parameters") or {})|dict(iterations=2 if fidelity=="screen" else 10)
                        if profile["task"]=="optimization":stage_config["iterations"]=10 if fidelity=="screen" else 30
                    stage_meta=metadata|dict(config=stage_config)
                    try:
                        stage_payload=(dict(data_spec=profile["data"],data_root=str(directory),task=profile["task"],config=stage_config,
                                            evaluator_hash=evaluator_version(),data_hash=profile["data_hash"],split_hash=profile["split_hash"])
                                       if real else dict(dataset=str(dataset),config=stage_config,evaluator_hash=evaluator_version(),**dataset_identity(data)))
                        key=controller.launch(campaign,stage_meta,provider,smoke_passed=smoke_passed,seconds=args.seconds,memory_mb=args.memory_mb,
                                              payload=stage_payload,
                                              fidelity=fidelity,branch=branch,parent=parent)
                    except sqlite3.IntegrityError:
                        from kaggle_agent.execution.gates import experiment_fingerprint
                        previous=store.rows("SELECT id,state FROM experiments WHERE competition=? AND fingerprint=?",(controller.competition,experiment_fingerprint(stage_meta)))
                        require(previous and previous[0]["state"]=="COMPLETED","Duplicate incomplete/failed trial requires explicit reviewed rerun")
                        store.event("duplicate_skipped",dict(config=stage_config,fidelity=fidelity),controller.competition)
                        parent=previous[0]["id"];duplicate=fidelity=="full"
                        continue
                    state=provider.reconcile(key)
                    if state["state"]!="COMPLETED":
                        controller.reconcile(provider)
                        if branch:portfolio.update(branch,execution_failed=True)
                        break
                    result=json.loads((jobs/key/"result.json").read_text())
                    controller.finish(key,result,jobs/key)
                    parent=key
                if duplicate:continue
                if key is None or state["state"]!="COMPLETED":break
                promotion=promote(store,controller.competition,key)
                if branch:portfolio.update(branch,standalone_gain=max(0.,promotion.get("mean_gain",0.)))
                with store.transaction() as db:
                    row=db.execute("SELECT result FROM experiments WHERE id=?",(key,)).fetchone()
                    stored=json.loads(row[0]);stored["standalone_improved"]=promotion["improved"]
                    db.execute("UPDATE experiments SET result=? WHERE id=?",(json.dumps(stored),key))
                completed.append(key)
            if profile["task"] in {"classification","regression"} and not controller.should_stop():
                if real:
                    blend=runs.assess_ensemble(store,controller,directory,profile)
                    ensemble_id=blend and blend.get("experiment")
                else:ensemble_id=assess_ensemble(store,controller,provider,dataset,data,profile,args.seconds,args.memory_mb)
                if ensemble_id:completed.append(ensemble_id)
            results=store.rows("SELECT state,fidelity,result FROM experiments WHERE competition=? ORDER BY created",(controller.competition,))
            check=stagnation([dict(state=r["state"],fidelity=r["fidelity"])|(json.loads(r["result"]) if r["result"] else {}) for r in results])
            checkpoint_value=checkpoint(store,controller.competition,check["next_action"],directory/".kaggle-agent"/"checkpoint.json")
            if check["research_review"]:
                store.event("research_review_required",check,controller.competition)
                from kaggle_agent.research.review import review_stagnation
                review_stagnation(store,controller.competition,directory,profile)
                break
        if controller.should_stop():transition(store,controller.competition,"STOPPED","user stop")
        return dict(completed=completed,state=store.rows("SELECT state FROM competitions WHERE id=?",(controller.competition,))[0]["state"],paid_cents=0)
    except KeyboardInterrupt:
        controller.request_stop()
        transition(store,controller.competition,"STOPPED","keyboard interrupt")
        return dict(state="STOPPED",completed=completed)
    except (ValueError,OSError,RuntimeError) as error:
        transition(store,controller.competition,"STOPPED" if "deadline" in str(error).lower() else "BLOCKED",str(error))
        raise
    finally:
        checkpoint(store,controller.competition,"inspect status and resume bounded campaign",directory/".kaggle-agent"/"checkpoint.json")
        export_state(store,controller.competition,directory)
        controller.release()


def usage(store):
    """Agent sessions per day and outcome. The plan usage itself is not visible to us;
    this shows how often sessions ran, hit limits or failed, and reported tokens."""
    rows=store.rows("SELECT agent,state,result,created FROM agent_sessions ORDER BY created")
    days={}
    for row in rows:
        day=row["created"][:10];entry=days.setdefault(day,dict(sessions=0,states={},input_tokens=0,output_tokens=0))
        entry["sessions"]+=1;entry["states"][row["state"]]=entry["states"].get(row["state"],0)+1
        try:tokens=(json.loads(row["result"]) or {}).get("usage") or {}
        except (TypeError,ValueError):tokens={}
        if isinstance(tokens,dict):
            entry["input_tokens"]+=int(tokens.get("input_tokens") or 0);entry["output_tokens"]+=int(tokens.get("output_tokens") or 0)
    limits=store.rows("SELECT created FROM events WHERE kind='transition' AND details LIKE '%WAITING_LIMIT%' ORDER BY created DESC LIMIT 5")
    return dict(days=days,recent_limit_hits=[r["created"] for r in limits])


def git_revision():
    result=subprocess.run(["git","rev-parse","HEAD"],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=5)
    return result.stdout.strip() if result.returncode==0 else "unknown"


def assess_ensemble(store,controller,provider,dataset,data,profile,seconds,memory_mb):
    from kaggle_agent.execution.identity import code_version
    from kaggle_agent.evaluation.validation import evaluator_version,promote
    from kaggle_agent.execution.gates import experiment_fingerprint
    comp=store.rows("SELECT champion FROM competitions WHERE id=?",(controller.competition,))[0]
    candidates=store.rows("SELECT e.*,p.path,p.checksum FROM experiments e JOIN predictions p ON p.experiment=e.id WHERE e.competition=? AND e.state='COMPLETED' AND e.fidelity='full' ORDER BY e.created DESC",(controller.competition,))
    candidates=[row for row in candidates if json.loads(row["result"])["score_type"]=="base_oof"]
    candidates.sort(key=lambda r:r["id"]!=comp["champion"])
    sources=[dict(path=row["path"],sha256=row["checksum"]) for row in candidates[:5]]
    if len(sources)<2:return None
    config=dict(metric=profile["metric"],seed=42,blend_sources=sources,baseline_index=0,_fidelity="full")
    metadata=dict(code_hash=code_version(),config=config,seed=42,metric=profile["metric"],evaluator_hash=evaluator_version(),
                  dataset_path=str(dataset),dataset_checksum=checksum(dataset),**dataset_identity(data),
                  hypothesis="Complementary frozen prediction library; conditional meta-CV versus identical single-base combiner",code_revision=git_revision())
    if store.rows("SELECT id FROM experiments WHERE competition=? AND fingerprint=?",(controller.competition,experiment_fingerprint(metadata))):return None
    campaign=controller.campaign(1)
    key=controller.launch(campaign,metadata,provider,smoke_passed=True,seconds=seconds,memory_mb=memory_mb,
                          payload=dict(dataset=str(dataset),config=config,evaluator_hash=evaluator_version(),**dataset_identity(data)))
    if provider.reconcile(key)["state"]!="COMPLETED":controller.reconcile(provider);return None
    root=provider.directory/key
    controller.finish(key,json.loads((root/"result.json").read_text()),root)
    promotion=promote(store,controller.competition,key,ensemble=True)
    with store.transaction() as db:
        row=db.execute("SELECT result FROM experiments WHERE id=?",(key,)).fetchone()
        result=json.loads(row[0]);result["ensemble_improved"]=promotion["improved"]
        db.execute("UPDATE experiments SET result=? WHERE id=?",(json.dumps(result),key))
        store.event("ensemble_assessment",dict(experiment=key,comparison=promotion),controller.competition,db)
    return key


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db",type=Path,default=home()/"global.sqlite3")
    sub=parser.add_subparsers(dest="command",required=True)
    sub.add_parser("doctor")
    budget_parser=sub.add_parser("budget")
    budget_parser.add_argument("--configure",type=Path)
    budget_parser.add_argument("--record-charge",type=Path)
    bench=sub.add_parser("benchmark");bench.add_argument("--output",type=Path,default=Path("benchmark-results"));bench.add_argument("--realistic",action="store_true")
    initializer=sub.add_parser("init");initializer.add_argument("--competition",required=True);initializer.add_argument("--task",choices=["classification","regression","optimization","forecasting"],default="classification");initializer.add_argument("--demo",action="store_true")
    for flag in ("--train","--test","--target","--metric","--direction","--group","--time","--scorer","--files","--solution-name"):initializer.add_argument(flag)
    initializer.add_argument("--id",default="id");initializer.add_argument("--folds",type=int,default=5);initializer.add_argument("--seed",type=int,default=42)
    limits_parser=sub.add_parser("limits");limits_parser.add_argument("--configure",type=Path)
    sub.add_parser("usage")
    register=sub.add_parser("register-run");register.add_argument("--competition",required=True)
    for flag in ("--oof","--test","--solution","--config","--hypothesis","--branch","--parent"):register.add_argument(flag)
    register.add_argument("--code",nargs="*",default=[]);register.add_argument("--fidelity",choices=["screen","intermediate","full"],default="full")
    register.add_argument("--seed",type=int)
    blend=sub.add_parser("blend");blend.add_argument("--competition",required=True)
    for name in ("audit","status","report","stop","export","migrate","checkpoint","start","resume"):
        command=sub.add_parser(name);command.add_argument("--competition",required=True)
        if name=="migrate":command.add_argument("--apply",action="store_true")
        if name in {"start","resume"}:
            command.add_argument("--agent",choices=["mock","codex","claude"],default="mock")
            command.add_argument("--mode",choices=["propose","code"],default="propose")
            command.add_argument("--execute",action="store_true")
            command.add_argument("--subscription-confirmed",action="store_true")
            command.add_argument("--campaigns",type=int,default=1);command.add_argument("--trials",type=int,default=1)
            command.add_argument("--seconds",type=float,default=None);command.add_argument("--memory-mb",type=int,default=None)
            command.add_argument("--config",type=Path)
    args=parser.parse_args(argv)
    try:
        if args.command=="doctor":
            result=dict(python=sys.version.split()[0],sqlite=sqlite3.sqlite_version,
                        agents={name:CLIAdapter(name).doctor() for name in ("codex","claude")},
                        paid_execution=False,submissions=False,global_database=str(args.db),
                        isolation="same-user processes: do not expose provider credentials to agents")
        elif args.command=="init":result=init(args.competition,args.task,args.demo,args)
        elif args.command=="benchmark":
            from kaggle_agent.benchmarks import benchmark,realistic_benchmark
            result=realistic_benchmark(args.output) if args.realistic else benchmark(args.output)
        else:
            store=Store(args.db)
            if args.command=="budget":
                budget=Budget(store)
                if args.configure:budget.configure(**json.loads(args.configure.read_text(encoding="utf-8")))
                if args.record_charge:budget.record_charge(**json.loads(args.record_charge.read_text(encoding="utf-8")))
                result=budget.summary()
            elif args.command in {"start","resume"}:result=run(args,store)
            elif args.command=="limits":
                from kaggle_agent.supervisor.limits import Limits,MAX_SECONDS,memory_ceiling_mb,machine_threads
                limits=Limits(store)
                if args.configure:limits.configure(**json.loads(args.configure.read_text(encoding="utf-8")))
                result=dict(limits=limits.get(),ceilings=dict(seconds=MAX_SECONDS,memory_mb=memory_ceiling_mb(),threads=machine_threads()))
            elif args.command=="usage":result=usage(store)
            elif args.command=="register-run":
                from kaggle_agent import runs
                directory,profile,controller=load_competition(args,store)
                config=json.loads(Path(args.config).read_text(encoding="utf-8")) if args.config else {}
                result=runs.register(store,controller,directory,profile,oof=args.oof,test=args.test,solution=args.solution,code=args.code,
                                     config=config,fidelity=args.fidelity,hypothesis=args.hypothesis or "manual run",branch=args.branch,
                                     parent=args.parent,seed=args.seed)
                export_state(store,controller.competition,directory)
            elif args.command=="blend":
                from kaggle_agent import runs
                directory,profile,controller=load_competition(args,store)
                controller.acquire()
                try:result=runs.assess_ensemble(store,controller,directory,profile) or dict(note="Need 2+ full runs (and a new combination) to blend")
                finally:controller.release()
                export_state(store,controller.competition,directory)
            elif args.command=="audit":
                root=Path(args.competition).resolve()
                result=dict(path=str(root),files={name:dict(bytes=(root/name).stat().st_size,sha256=checksum(root/name)) for name in LEGACY if (root/name).is_file()},
                            migration=migrate(store,root),note="Inventory only; no legacy authority inferred; review manual limits")
            elif args.command=="migrate":result=migrate(store,args.competition,apply=args.apply)
            else:
                directory=Path(args.competition).resolve()
                stored=store.rows("SELECT * FROM competitions WHERE id=?",(competition_id(directory),))
                if stored:
                    profile=json.loads(stored[0]["profile"]);controller=Controller(store,competition_id(directory))
                else:directory,profile,controller=load_competition(args,store)
                key=controller.competition
                if args.command=="stop":
                    controller.request_stop();result=dict(stop_requested=True,next_action="Active controller checkpoints and terminates its local child")
                elif args.command=="export":result=dict(directory=export_state(store,key,directory))
                elif args.command=="checkpoint":result=checkpoint(store,key,"review then resume",directory/".kaggle-agent"/"checkpoint.json")
                else:
                    result=dict(competition=store.rows("SELECT * FROM competitions WHERE id=?",(key,)),
                                experiments=store.rows("SELECT id,state,fidelity,result,failure_reason FROM experiments WHERE competition=? ORDER BY created",(key,)),
                                jobs=store.rows("SELECT j.* FROM remote_jobs j JOIN experiments e ON j.experiment=e.id WHERE e.competition=?",(key,)),budget=Budget(store).summary())
        print(json.dumps(result,indent=2,allow_nan=False));return 0
    except (ValueError,OSError,RuntimeError,sqlite3.Error) as error:
        print(json.dumps(dict(error=type(error).__name__,reason=str(error))),file=sys.stderr);return 2


if __name__=="__main__":raise SystemExit(main())
