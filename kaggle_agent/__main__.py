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


def init(directory,task,demo=False):
    root=Path(directory).resolve()
    require(root.is_dir(),"Competition directory must exist")
    folder=root/".kaggle-agent";profile_path=folder/"profile.json"
    require(not profile_path.exists(),"Profile already exists; inspect/version it explicitly")
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
        return dict(data_hash=fingerprint(dict(ids=data["ids"],y=data["y"])),split_hash=fingerprint(dict(ids=data["ids"],folds=data["folds"])))
    return dict(data_hash=fingerprint(data),split_hash=fingerprint({k:data[k] for k in ("origins","horizon","times") if k in data} or dict(exact=True)))


def load_competition(args,store):
    directory=Path(args.competition).resolve()
    path=directory/".kaggle-agent"/"profile.json"
    require(path.is_file(),"Run init first, then review profile and dataset")
    profile=json.loads(path.read_text(encoding="utf-8"))
    validate_profile(profile)
    controller=Controller(store,competition_id(directory));controller.register(directory,profile)
    return directory,profile,controller


def run(args,store):
    directory,profile,controller=load_competition(args,store)
    dataset=directory/".kaggle-agent"/"dataset.json"
    require(dataset.is_file(),"Frozen dataset.json required; see operating guide")
    data=json.loads(dataset.read_text(encoding="utf-8"))
    require(dataset_identity(data)=={k:profile[k] for k in ("data_hash","split_hash")},"Dataset/split profile mismatch")
    require(data["task"]==profile["task"],"Dataset task mismatch")
    require(profile.get("legacy_limits_reviewed",False),"Review legacy CONFIG/STATE limits and active jobs before setting legacy_limits_reviewed=true")
    require(0<args.seconds<=min(1800,profile["constraints"].get("seconds",1800)) and 0<args.memory_mb<=min(2048,profile["constraints"].get("memory_mb",2048)),"Resource bounds exceed approved/profile caps")
    require(1<=args.campaigns<=20 and 1<=args.trials<=4,"Bound campaigns to 1..20 and trials to 1..4")
    config=json.loads(Path(args.config).read_text()) if args.config else dict(seed=42,metric=profile["metric"])
    require(config.get("metric")==profile["metric"],"Config metric mismatch")
    if not args.execute:
        return dict(dry_run=True,agent=args.agent,campaigns=args.campaigns,trials=args.trials,config=config,
                    paid_execution=False,submissions=False,next_action="Use --execute for bounded local CPU execution")
    require(args.agent=="mock" or args.subscription_confirmed,"Confirm installed CLI uses selected subscription before agent execution")
    from kaggle_agent.execution.local import LocalProvider
    from kaggle_agent.execution.identity import code_version
    from kaggle_agent.evaluation.validation import evaluator_version,promote
    from kaggle_agent.research.branches import Portfolio,stagnation
    controller.acquire()
    jobs=directory/".kaggle-agent"/"jobs"
    provider=LocalProvider(jobs,seconds=args.seconds,memory_mb=args.memory_mb,heartbeat=controller.heartbeat,should_stop=controller.should_stop)
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
            agent_result=agent.resume("Review next bounded research task; report protocol JSON. No remote actions.",directory,cp,
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
                if args.trials>1:
                    if profile["task"] in {"classification","regression"}:trial_config["family"]=("linear","forest","hist","linear")[trial]
                    elif profile["task"]=="optimization":trial_config["operator"]=("greedy","local","anneal","restart")[trial]
                    else:trial_config["family"]=("seasonal_naive","lag_ridge","lag_boosting","seasonal_naive")[trial]
                    trial_config["seed"]=config.get("seed",42)+campaign_index*4+trial
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
                metadata=dict(code_hash=code_version(),config=trial_config,seed=trial_config.get("seed",42),metric=profile["metric"],
                              evaluator_hash=evaluator_version(),dataset_path=str(dataset),dataset_checksum=checksum(dataset),
                              **dataset_identity(data),hypothesis="bounded local baseline/portfolio trial",code_revision=git_revision())
                try:
                    key=controller.launch(campaign,metadata,provider,smoke_passed=smoke_passed,seconds=args.seconds,memory_mb=args.memory_mb,
                                          payload=dict(dataset=str(dataset),config=trial_config,evaluator_hash=evaluator_version(),**dataset_identity(data)))
                except sqlite3.IntegrityError:
                    store.event("duplicate_skipped",dict(config=trial_config),controller.competition)
                    continue
                state=provider.reconcile(key)
                if state["state"]!="COMPLETED":
                    controller.reconcile(provider)
                    break
                result=json.loads((jobs/key/"result.json").read_text())
                controller.finish(key,result,jobs/key)
                promotion=promote(store,controller.competition,key)
                with store.transaction() as db:
                    row=db.execute("SELECT result FROM experiments WHERE id=?",(key,)).fetchone()
                    stored=json.loads(row[0]);stored["standalone_improved"]=promotion["improved"]
                    db.execute("UPDATE experiments SET result=? WHERE id=?",(json.dumps(stored),key))
                completed.append(key)
            results=store.rows("SELECT state,result FROM experiments WHERE competition=? ORDER BY created",(controller.competition,))
            check=stagnation([dict(state=r["state"])|(json.loads(r["result"]) if r["result"] else {}) for r in results])
            checkpoint_value=checkpoint(store,controller.competition,check["next_action"],directory/".kaggle-agent"/"checkpoint.json")
            if check["research_review"]:
                store.event("research_review_required",check,controller.competition)
                transition(store,controller.competition,"BLOCKED","eight completed no-progress trials; research review required")
                break
        if controller.should_stop():transition(store,controller.competition,"STOPPED","user stop")
        return dict(completed=completed,state=store.rows("SELECT state FROM competitions WHERE id=?",(controller.competition,))[0]["state"],paid_cents=0)
    except KeyboardInterrupt:
        controller.request_stop()
        transition(store,controller.competition,"STOPPED","keyboard interrupt")
        return dict(state="STOPPED",completed=completed)
    except (ValueError,OSError,RuntimeError) as error:
        transition(store,controller.competition,"BLOCKED",str(error))
        raise
    finally:
        checkpoint(store,controller.competition,"inspect status and resume bounded campaign",directory/".kaggle-agent"/"checkpoint.json")
        export_state(store,controller.competition,directory)
        controller.release()


def git_revision():
    result=subprocess.run(["git","rev-parse","HEAD"],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=5)
    return result.stdout.strip() if result.returncode==0 else "unknown"


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db",type=Path,default=home()/"global.sqlite3")
    sub=parser.add_subparsers(dest="command",required=True)
    sub.add_parser("doctor");sub.add_parser("budget")
    bench=sub.add_parser("benchmark");bench.add_argument("--output",type=Path,default=Path("benchmark-results"))
    initializer=sub.add_parser("init");initializer.add_argument("--competition",required=True);initializer.add_argument("--task",choices=["classification","regression","optimization","forecasting"],default="classification");initializer.add_argument("--demo",action="store_true")
    for name in ("audit","status","report","stop","export","migrate","checkpoint","start","resume"):
        command=sub.add_parser(name);command.add_argument("--competition",required=True)
        if name=="migrate":command.add_argument("--apply",action="store_true")
        if name in {"start","resume"}:
            command.add_argument("--agent",choices=["mock","codex","claude"],default="mock")
            command.add_argument("--execute",action="store_true")
            command.add_argument("--subscription-confirmed",action="store_true")
            command.add_argument("--campaigns",type=int,default=1);command.add_argument("--trials",type=int,default=1)
            command.add_argument("--seconds",type=float,default=60);command.add_argument("--memory-mb",type=int,default=1024)
            command.add_argument("--config",type=Path)
    args=parser.parse_args(argv)
    try:
        if args.command=="doctor":
            result=dict(python=sys.version.split()[0],sqlite=sqlite3.sqlite_version,
                        agents={name:CLIAdapter(name).doctor() for name in ("codex","claude")},
                        paid_execution=False,submissions=False,global_database=str(args.db),
                        isolation="same-user processes: do not expose provider credentials to agents")
        elif args.command=="init":result=init(args.competition,args.task,args.demo)
        elif args.command=="benchmark":
            from kaggle_agent.benchmarks import benchmark
            result=benchmark(args.output)
        else:
            store=Store(args.db)
            if args.command=="budget":result=Budget(store).summary()
            elif args.command in {"start","resume"}:result=run(args,store)
            elif args.command=="audit":
                root=Path(args.competition).resolve()
                result=dict(path=str(root),files={name:dict(bytes=(root/name).stat().st_size,sha256=checksum(root/name)) for name in LEGACY if (root/name).is_file()},
                            migration=migrate(store,root),note="Inventory only; no legacy authority inferred; review manual limits")
            elif args.command=="migrate":result=migrate(store,args.competition,apply=args.apply)
            else:
                directory,profile,controller=load_competition(args,store)
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
