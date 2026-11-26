"""ka: the short command for everyday use.

    ka setup                 one-time: agent, CPU/RAM, alerts
    ka new <kaggle url>      folder + download + detect columns/metric + freeze folds
    ka go                    run (or resume) the code-writing loop, live progress
    ka status                short summary
    ka dash                  open the progress page in your browser
    ka submit [run-id]       send the best run now   (ka submit --auto on|off, --limit N)
    ka stop                  ask a running `ka go` to stop safely
    ka usage                 agent sessions per day
    ka research              read public notebooks + forum threads now (also runs inside ka go)
    ka agent [claude|codex]  show or set model and effort (--model X --effort high, --global)
    ka history               code version of every scored run (git)
    ka diff [run-id]         what changed versus the champion
    ka restore <run-id>      copy a past run's code into restored/<run-id>/

Run every command except setup and new from inside the competition folder.
The long `python -m kaggle_agent ...` commands still work for advanced use.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import webbrowser

from kaggle_agent.execution.gates import GateError

SHARED = Path(__file__).resolve().parents[1]


def home():
    return Path(os.environ.get("KAGGLE_AGENT_HOME", str(Path.home() / ".kaggle-agent"))).resolve()


def db_path():
    return home() / "global.sqlite3"


def load_settings():
    path = home() / "settings.json"
    defaults = dict(agent="claude", campaigns=2, trials=4, competitions_root=str(SHARED.parent), alerts={})
    return defaults | (json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {})


def save_settings(value):
    home().mkdir(parents=True, exist_ok=True)
    (home() / "settings.json").write_text(json.dumps(value, indent=2), encoding="utf-8")


def agent_file(directory):
    return Path(directory) / ".kaggle-agent" / "agent.json"


def agent_choice(settings, directory, name):
    """Model and effort for one agent: this competition's agent.json beats the global
    setup value. Empty means the tool's own default."""
    merged = {}
    sources = [(settings.get("agents") or {}).get(name) or {}]
    path = agent_file(directory) if directory else None
    if path and path.is_file():
        sources.append((json.loads(path.read_text(encoding="utf-8")) or {}).get(name) or {})
    for source in sources:
        merged.update({k: v for k, v in source.items() if k in {"model", "effort"} and v})
    return merged


def describe_choice(choice):
    return f"model {choice.get('model') or 'default'}, effort {choice.get('effort') or 'default'}"


def ask_console(question, default=None):
    suffix = f" [{default}]" if default not in (None, "") else ""
    answer = input(f"{question}{suffix}: ").strip()
    return answer or (default if default is not None else "")


def yes(answer):
    return str(answer).strip().lower() in {"y", "yes"}


def find_competition(start=None):
    folder = Path(start or os.getcwd()).resolve()
    for candidate in [folder, *folder.parents]:
        if (candidate / ".kaggle-agent" / "profile.json").is_file():
            return candidate
    raise GateError("Not inside a competition folder. cd into one, or create it with: ka new <kaggle url>")


def store():
    from kaggle_agent.storage.database import Store
    return Store(db_path())


def controller_for(directory, st):
    from kaggle_agent.__main__ import load_competition
    return load_competition(argparse.Namespace(competition=str(directory)), st)


# ---------------------------------------------------------------- setup
def cmd_setup(args, ask):
    from kaggle_agent.agents.base import CLIAdapter
    from kaggle_agent.supervisor.limits import Limits, machine_memory_mb, machine_threads, memory_ceiling_mb
    settings = load_settings()
    print("Checking tools...")
    found = {name: CLIAdapter(name).doctor() for name in ("claude", "codex")}
    for name, info in found.items():
        state = "ready" if info.get("available") else info.get("reason") or ("missing flags: " + ", ".join(info.get("missing_flags", [])))
        print(f"  {name}: {state} {info.get('version', '')}")
    try:
        from kaggle_agent import kaggle_cli
        kaggle_cli.command()
        print("  kaggle CLI: ready")
    except Exception as error:
        print(f"  kaggle CLI: {error}")
    ready = [n for n, i in found.items() if i.get("available")]
    def collect(settings, current_limits):
        agent = ask("Which agent should write the code (claude/codex)?", settings["agent"] if settings["agent"] in ready or not ready else ready[0])
        if agent not in {"claude", "codex"}:
            raise GateError("Choose claude or codex")
        agents = settings.get("agents") or {}
        current = agents.get(agent) or {}
        model = ask(f"{agent} model (empty = {agent}'s own default)", current.get("model", ""))
        effort = ask(f"{agent} effort: low, medium, high, xhigh (empty = default)", current.get("effort", ""))
        CLIAdapter(agent, model=model, effort=effort)   # validates the effort word
        agents[agent] = {k: v for k, v in dict(model=model.strip(), effort=effort.strip().lower()).items() if v}
        threads = int(ask(f"CPU threads per run (this machine has {machine_threads()})", str(current_limits.get("threads") or max(1, machine_threads() // 2))))
        memory = int(ask(f"Memory per run in MB (machine {machine_memory_mb()}, max {memory_ceiling_mb()})", str(current_limits.get("memory_mb") or min(8192, memory_ceiling_mb()))))
        hours = float(ask("Max hours per run", f"{(current_limits.get('seconds') or 3600) / 3600:g}"))
        campaigns = int(ask("Campaigns per `ka go`", str(settings["campaigns"])))
        trials = int(ask("Trials per campaign (1-4)", str(settings["trials"])))
        alerts = settings.get("alerts") or {}
        choice = ask("Phone alerts: ntfy, telegram or none?", "ntfy" if alerts.get("ntfy_topic") else "telegram" if alerts.get("telegram_token") else "none").lower()
        if choice == "ntfy":
            import secrets
            topic = ask("ntfy topic (keep it secret; subscribe to it in the ntfy app)", alerts.get("ntfy_topic") or "ka-" + secrets.token_hex(6))
            alerts = dict(ntfy_topic=topic)
        elif choice == "telegram":
            alerts = dict(telegram_token=ask("Telegram bot token", alerts.get("telegram_token", "")),
                          telegram_chat=ask("Telegram chat id", alerts.get("telegram_chat", "")))
        else:
            alerts = {}
        return dict(agent=agent, agents=agents, campaigns=campaigns, trials=trials, alerts=alerts, threads=threads, memory=memory, hours=hours)
    limits_now = {k: v for k, v in Limits(store()).get().items() if k in {"threads", "memory_mb", "seconds"}}
    while True:
        got = collect(settings, limits_now)
        print("\nYour answers:")
        print(f"  agent {got['agent']} ({describe_choice(got['agents'].get(got['agent'], {}))}) · threads {got['threads']} · memory {got['memory']} MB · "
              f"{got['hours']:g} h per run · {got['campaigns']} campaigns × {got['trials']} trials · alerts: "
              + ("ntfy" if got["alerts"].get("ntfy_topic") else "telegram" if got["alerts"].get("telegram_token") else "none"))
        if ask("Save these? y = save, n = answer again (your answers become the defaults)", "y").strip().lower() in {"y", "yes", ""}:
            break
        settings.update(agent=got["agent"], agents=got["agents"], campaigns=got["campaigns"], trials=got["trials"], alerts=got["alerts"])
        limits_now = dict(threads=got["threads"], memory_mb=got["memory"], seconds=int(got["hours"] * 3600))
    agent, agents, campaigns, trials, alerts = got["agent"], got["agents"], got["campaigns"], got["trials"], got["alerts"]
    threads, memory, hours = got["threads"], got["memory"], got["hours"]
    settings.update(agent=agent, agents=agents, campaigns=campaigns, trials=trials, alerts=alerts)
    save_settings(settings)
    from kaggle_agent.supervisor.budget import Budget
    budget = Budget(store())
    if not budget.summary()["config"]["confirmed"]:
        # Local runs and your existing subscription cost nothing extra; paid APIs stay blocked.
        budget.configure(confirmed=True, fixed_cents=0, reserve_cents=500)
    Limits(store()).configure(threads=threads, memory_mb=memory, seconds=int(hours * 3600),
                              max_iterations=max(20000, Limits(store()).get()["max_iterations"]))
    if alerts:
        from kaggle_agent import notify
        notify.send(settings, "ka setup", "Alerts are working.")
        print("Sent a test alert.")
    print("Saved. Next: ka new <kaggle competition url>")
    return 0


# ---------------------------------------------------------------- new
def find_file(folder, stem):
    options = sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in {".csv", ".parquet"}
                     and p.stem.lower().startswith(stem))
    exact = [p for p in options if p.stem.lower() == stem]
    return (exact or options or [None])[0]


def detect(data_dir):
    """Guess files, id, target, task and a time column from the downloaded data."""
    import pandas as pd
    from pandas.api.types import is_numeric_dtype, is_float_dtype
    from kaggle_agent import data as tables
    train, test, sample = find_file(data_dir, "train"), find_file(data_dir, "test"), find_file(data_dir, "sample_submission")
    if train is None or test is None:
        raise GateError("Could not find train and test files in data/. Is this a code or optimization competition? "
                        "For optimization use: ka new <url> --optimization --scorer my_scorer.py --solution-name submission.csv")
    head = lambda p: pd.read_csv(p, nrows=5000) if p.suffix.lower() == ".csv" else tables.read_table(p).head(5000)
    tr, te = head(train), head(test)
    sm = head(sample) if sample is not None else None
    id_col = sm.columns[0] if sm is not None and sm.columns[0] in tr.columns else next((c for c in tr.columns if c.lower() in {"id", "row_id"}), tr.columns[0])
    candidates = [c for c in tr.columns if c not in te.columns and c != id_col]
    if sm is not None:
        preferred = [c for c in sm.columns[1:] if c in candidates]
        candidates = preferred or candidates
    target = candidates[0] if len(candidates) == 1 else (candidates[0] if candidates else None)
    task = None
    if target is not None:
        y = tr[target]
        task = "regression" if is_numeric_dtype(y) and (is_float_dtype(y) and y.nunique() > 20 or y.nunique() > 50) else "classification"
    time_col = next((c for c in tr.columns if any(k in c.lower() for k in ("date", "time", "timestamp")) and c != target), None)
    return dict(train=train, test=test, sample=sample, id=id_col, target=target, task=task, time=time_col,
                other_targets=candidates[1:])


def cmd_new(args, ask):
    from kaggle_agent import kaggle_cli
    from kaggle_agent import submit as submissions
    from kaggle_agent.__main__ import init
    from kaggle_agent.initialize import initialize
    settings = load_settings()
    slug = kaggle_cli.slug_from(args.url)
    url = f"https://www.kaggle.com/competitions/{slug}"
    parent = Path(args.root or settings["competitions_root"]).resolve()
    target = parent / (args.folder or slug)
    if (target / ".kaggle-agent" / "profile.json").exists():
        raise GateError(f"{target} is already set up. cd there and run: ka go")
    if not target.exists():
        initialize(parent, target.name, url, shared=SHARED)
        print(f"Created {target}")
    data_dir = target / "data"
    if not args.no_download:
        print(f"Downloading {slug} ...")
        try:
            kaggle_cli.download(slug, data_dir)
        except kaggle_cli.KaggleError as error:
            if "rules" in str(error).lower() or "refused" in str(error).lower():
                webbrowser.open(url + "/rules")
            raise GateError(str(error))
    facts = kaggle_cli.info(slug)
    if args.optimization:
        return new_optimization(args, ask, target, slug, facts)
    found = detect(data_dir)
    metric = kaggle_cli.map_metric(facts.get("metric"))
    print("\nDetected:")
    print(f"  train:  {found['train'].relative_to(target)}\n  test:   {found['test'].relative_to(target)}")
    print(f"  sample: {found['sample'].relative_to(target) if found['sample'] else 'none (auto-submit unavailable)'}")
    print(f"  id: {found['id']}   target: {found['target']}   task: {found['task']}")
    print(f"  metric: {metric or 'unknown'}" + (f"   (Kaggle says: {facts.get('metric')})" if facts.get("metric") else ""))
    if found["other_targets"]:
        print(f"  note: other train-only columns: {', '.join(found['other_targets'])}")
    if args.yes and found["target"] and found["task"] and metric:
        pass
    elif not yes(ask("Is this right? (y/n)", "y")):
        found["id"] = ask("ID column", found["id"])
        found["target"] = ask("Target column", found["target"] or "")
        found["task"] = ask("Task (classification/regression)", found["task"] or "classification")
        metric = None
    if not metric:
        metric = ask("Metric (roc_auc, log_loss, accuracy, balanced_accuracy, map3, rmse, mae, rmsle, r2, mape)",
                     "roc_auc" if found["task"] == "classification" else "rmse")
    time_col = None
    if found["time"] and not args.yes:
        if yes(ask(f"Use time-ordered folds on '{found['time']}' (for forecasting)? (y/n)", "n")):
            time_col = found["time"]
    rel = lambda p: os.path.relpath(p, target)
    init_args = argparse.Namespace(train=str(found["train"]), test=str(found["test"]), target=found["target"], id=found["id"],
                                   metric=metric, direction=None, group=None, time=time_col, folds=args.folds, seed=42,
                                   scorer=None, files=None, solution_name=None)
    init(target, "forecasting" if time_col else found["task"], False, init_args)
    finish_new(args, ask, target, slug, facts, sample=rel(found["sample"]) if found["sample"] else None)
    return 0


def new_optimization(args, ask, target, slug, facts):
    from kaggle_agent.__main__ import init
    if not args.scorer or not args.solution_name:
        raise GateError("Optimization needs --scorer my_scorer.py (score(solution_path, data_dir) -> float) and --solution-name")
    files = [os.path.relpath(p, target) for p in sorted((target / "data").rglob("*")) if p.is_file() and p.suffix.lower() != ".zip"]
    direction = args.direction or ask("Is a lower or higher score better? (minimize/maximize)", "minimize")
    init_args = argparse.Namespace(train=None, test=None, target=None, id="id", metric="objective", direction=direction, group=None,
                                   time=None, folds=5, seed=42, scorer=args.scorer, files=",".join(files), solution_name=args.solution_name)
    init(target, "optimization", False, init_args)
    finish_new(args, ask, target, slug, facts, sample=None)
    return 0


def finish_new(args, ask, target, slug, facts, *, sample):
    from kaggle_agent import submit as submissions
    path = target / ".kaggle-agent" / "profile.json"
    profile = json.loads(path.read_text(encoding="utf-8"))
    rules = args.yes or yes(ask(f"Have you read the competition rules (https://www.kaggle.com/competitions/{slug}/rules)? (y/n)", "n"))
    profile["rules_reviewed"] = bool(rules)
    deadline = facts.get("deadline")
    if deadline:
        profile["deadline"] = deadline if ("+" in deadline[10:] or deadline.endswith("Z")) else deadline + "+00:00"
        profile["deadline"] = profile["deadline"].replace("Z", "+00:00")
    path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    auto = False
    if sample or profile["task"] == "optimization":
        auto = yes(ask("Turn on auto-submit (sends each new best run, keeps 1 daily slot for you)? (y/n)", "n")) and not args.yes
    limit = facts.get("daily_limit")
    if not limit:
        limit = 5 if args.yes else int(ask("Daily submission limit (see the competition Overview or Rules page)", "5") or 5)
    else:
        print(f"Daily submission limit (from Kaggle): {limit}")
    submissions.save_settings(target, slug=slug, sample=sample, auto=auto, daily_limit=int(limit), reserve=1)
    try:
        from kaggle_agent import vcs
        vcs.ensure_repo(target)
        print("Git history: on (local only; code is committed after every scored run)")
    except Exception as error:
        print(f"Git history: off ({error}). Install Git for Windows to version the code.")
    task = target / ".kaggle-agent" / "task.md"
    if not task.exists():
        task.write_text(f"# {slug}: competition rules\n\n(Paste the Overview > Evaluation section and the Data page rules here.\n"
                        "The agent reads this file in every brief.)\n", encoding="utf-8")
    print(f"Paste the competition's rules (Overview > Evaluation, and the Data page) into {task}. "
          "The agent reads it before every trial" + (" and needs it for optimization puzzles." if profile["task"] == "optimization" else "."))
    print(f"\nReady: {target}")
    if not rules:
        print("Read the rules, then set \"rules_reviewed\": true in .kaggle-agent/profile.json before `ka go`.")
    print(f"Next:\n  cd \"{target}\"\n  ka go")


# ---------------------------------------------------------------- go
def printer(settings, st, directory, profile, competition):
    from kaggle_agent import notify
    from kaggle_agent import submit as submissions
    state = dict(champion=False)

    def on_event(kind, **d):
        if kind == "trial_start":
            print(f"\nCampaign {d['campaign']}/{d['campaigns']} · trial {d['trial']}/{d['trials']} · branch {d['branch']} · agent writing code...", flush=True)
        elif kind == "research_start":
            print("Reading public notebooks and forum posts (first time can take a few minutes)...", flush=True)
        elif kind == "research":
            got = [f"{d['notebooks']} notebooks" + (f" ({d['skipped_notebooks']} empty/copies skipped)" if d.get("skipped_notebooks") else "") if "notebooks" in d else "", f"{d['discussions']} forum threads" if "discussions" in d else ""]
            got = ", ".join(x for x in got if x)
            if not got:
                notes = []
                for name, label in (("notebooks", "notebooks"), ("discussions", "forum threads")):
                    why = d.get(name + "_skipped")
                    if why:
                        notes.append(f"{label} " + ("up to date (read within the last day)" if why == "recent" else "will retry later"))
                got = "; ".join(notes) or "nothing new"
            print(f"  research: {got}" + "".join(f"\n  research problem: {e}" for e in d.get("errors", [])), flush=True)
        elif kind == "research_analysis":
            if d.get("analyzed"):
                print(f"  findings: {d['analyzed']} new notes read, {d['findings']} findings saved, {d['branches']} new ideas queued"
                      + (f", {d['ignored']} rated no-value" if d.get("ignored") else "")
                      + (f" ({d['waiting']} notes waiting)" if d.get("waiting") else ""), flush=True)
            elif d.get("error"):
                print(f"  findings problem: {d['error']} (notes stay pending)", flush=True)
        elif kind == "agent_done":
            print(f"  idea: {d['hypothesis']}", flush=True)
        elif kind == "stage":
            print(f"  {d['fidelity']}: {d['mean']:.6g} (±{d['std']:.2g})", flush=True)
        elif kind == "outcome":
            text = d["outcome"]
            if text == "champion":
                state["champion"] = True
                if isinstance(d.get("mean"), (int, float)):
                    state["best"] = d["mean"]   # champions only improve, so the last one is the best
                gain = d.get("gain")
                text = "NEW CHAMPION" + (f" (+{abs(gain):.4g})" if isinstance(gain, (int, float)) and gain else "")
                notify.send(settings, "New champion", f"{Path(directory).name}: {d.get('mean', 0):.6g} · {d.get('hypothesis', '')[:120]}")
            print(f"  → {text}" + (f": {d['detail'][-200:]}" if d.get("detail") else ""), flush=True)
        elif kind == "blend":
            promo = d.get("promotion") or {}
            if d.get("error"):
                print(f"  blend skipped: {d['error']}")
                return
            mean = sum(d["fold_scores"]) / len(d["fold_scores"])
            print(f"Blend ({d.get('combiner')}): {mean:.6g}" + (" → new ensemble champion" if promo.get("improved") else " → no gain"), flush=True)
            if promo.get("improved"):
                state["champion"] = True
        elif kind == "campaign_end":
            best = state.get("best")
            line = f"Campaign {d.get('campaign')}/{d.get('campaigns')} done"
            if best is not None:
                line += f" · best score {best:.6g}"
            tokens = d.get("tokens") or {}
            if tokens:
                short = lambda n: f"{n / 1e6:.1f}M" if n >= 1e6 else f"{n / 1e3:.0f}k" if n >= 1e3 else str(n)
                line += " · tokens: " + ", ".join(f"{short(tokens[k])} {k}" for k in ("input", "output", "cached") if tokens.get(k))
            print(line, flush=True)
            if state["champion"]:
                state["champion"] = False
                try:
                    sent = submissions.maybe_auto(st, competition, directory, profile)
                except GateError as error:
                    sent = dict(sent=False, reason=str(error))
                if sent:
                    line = f"auto-submitted {sent['experiment'][:8]} (cv {sent['cv']:.6g})" if sent.get("sent") else \
                           f"auto-submit skipped: {sent.get('reason') or sent.get('error')}"
                    print(f"  {line}", flush=True)
                    notify.send(settings, "Submission", f"{Path(directory).name}: {line}")
            if d.get("stuck"):
                print("  8 runs without progress: research review written (.kaggle-agent/research-review.json)")
                notify.send(settings, "Stuck", f"{Path(directory).name}: research review needed")
        elif kind == "stopped":
            print(f"\nStopped: {d['state']} ({d['reason']})", flush=True)
            hint = STOP_HINTS.get(d["reason"])
            if hint:
                print(hint, flush=True)
            notify.send(settings, "Run stopped", f"{Path(directory).name}: {d['state']} ({d['reason']})")
    return on_event


STOP_HINTS = {
    "authentication": "The agent CLI is not logged in (or its login expired). Run `claude auth login` "
                      "(or `codex login`, choosing your ChatGPT account), then `ka go` again. For long unattended "
                      "runs, `claude setup-token` creates a long-lived subscription token.",
    "usage_limit": "Your plan's usage limit was reached. Progress is saved: run `ka go` again after it resets.",
    "missing_binary": "The agent CLI was not found. Install Claude Code or Codex, or switch with `ka go --agent codex`.",
    "agent_exit": "The agent CLI exited with an error. Its log is in .kaggle-agent\\sessions\\ (newest folder, output.log).",
    "malformed_output": "The agent answered without the expected JSON. Run `ka go` again; if it repeats, send the session log.",
}


def cmd_go(args, ask):
    from kaggle_agent.__main__ import run
    from kaggle_agent.agents.base import CLIAdapter
    from kaggle_agent.dashboard import build
    from kaggle_agent import notify
    settings = load_settings()
    directory = find_competition(args.dir)
    profile = json.loads((directory / ".kaggle-agent" / "profile.json").read_text(encoding="utf-8"))
    if not profile.get("rules_reviewed"):
        raise GateError("Read the competition rules, then set \"rules_reviewed\": true in .kaggle-agent/profile.json")
    agent_name = args.agent or settings["agent"]
    st = store()
    from kaggle_agent.__main__ import competition_id
    competition = competition_id(directory)
    exists = st.rows("SELECT state,stop_requested FROM competitions WHERE id=?", (competition,))
    command = "resume" if exists and (exists[0]["stop_requested"] or exists[0]["state"] in {"STOPPED", "BLOCKED", "WAITING_LIMIT", "FAILED"}) else "start"
    choice = agent_choice(settings, directory, agent_name)
    agent = getattr(args, "mock_agent", None) or CLIAdapter(agent_name, **choice)
    run_args = argparse.Namespace(competition=str(directory), agent="mock" if getattr(args, "mock_agent", None) else agent_name, mode="code",
                                  execute=True, subscription_confirmed=True, campaigns=args.campaigns or settings["campaigns"],
                                  trials=args.trials or settings["trials"], seconds=None, memory_mb=None, config=None,
                                  command=command, mock_agent=agent)
    if run_args.agent != "mock":
        from kaggle_agent.supervisor.budget import Budget
        if not Budget(st).summary()["config"]["confirmed"]:
            raise GateError("Run `ka setup` once first (it confirms you use your existing Claude/Codex plan, no paid API).")
    print(f"{'Resuming' if command == 'resume' else 'Starting'} {directory.name} with {agent_name} ({describe_choice(choice)}) · "
          f"{run_args.campaigns} campaign(s) × {run_args.trials} trial(s). Stop any time with Ctrl+C or `ka stop`.")
    print(f"Progress page: {directory / '.kaggle-agent' / 'views' / 'dashboard.html'}")
    refresh_limit(directory)
    on_event = printer(settings, st, directory, profile, competition)
    try:
        result = run_with_events(run_args, st, on_event)
    except GateError as error:
        notify.send(settings, "Run blocked", f"{directory.name}: {error}")
        raise
    print(f"\nDone: {result.get('state')} · {len(result.get('completed', []))} new run(s). See `ka status` or `ka dash`.")
    notify.send(settings, "Campaigns finished", f"{directory.name}: {result.get('state')}")
    return 0


def cmd_research(args, ask):
    """Read public notebooks and forum threads now, and show where the notes are."""
    from kaggle_agent import submit as submissions
    from kaggle_agent.research import public
    directory = find_competition(args.dir)
    slug = submissions.settings(directory).get("slug")
    if not slug:
        raise GateError("This competition has no Kaggle slug; set it up with `ka new <url>`")
    print("Reading public notebooks and forum posts (first time can take a few minutes)...")
    report = public.refresh(directory, slug, force=True)
    root = public.folder(directory)
    print(f"Notebooks: {report.get('notebooks', 0)} saved ({report.get('new_notebooks', 0)} new) · forum threads: {report.get('discussions', 0)}")
    for error in report["errors"]:
        print(f"Problem: {error}")
    print(f"Notes are plain files in: {root}\n  summary.md (what the agent sees), notebooks/, discussions/")
    return 1 if report["errors"] and not (report.get("notebooks") or report.get("discussions")) else 0


def cmd_agent(args, ask):
    """Show or set model and effort. Per competition by default; --global for all."""
    settings = load_settings()
    names = [args.name] if args.name else ["claude", "codex"]
    changes = {k: v for k, v in dict(model=args.model, effort=args.effort).items() if v is not None}
    if changes:
        if not args.name:
            raise GateError("Say which agent: ka agent claude --effort high  (or codex)")
        from kaggle_agent.agents.base import CLIAdapter
        CLIAdapter(args.name, **changes)   # validates the effort word
        changes = {k: v.strip().lower() if k == "effort" else v.strip() for k, v in changes.items()}
        if args.use_global:
            agents = settings.get("agents") or {}
            agents.setdefault(args.name, {}).update(changes)
            agents[args.name] = {k: v for k, v in agents[args.name].items() if v}
            settings["agents"] = agents
            save_settings(settings)
            scope = "all competitions"
            directory = None
        else:
            directory = find_competition(args.dir)
            path = agent_file(directory)
            data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
            data.setdefault(args.name, {}).update(changes)
            data[args.name] = {k: v for k, v in data[args.name].items() if v}
            path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            scope = directory.name
        print(f"Saved for {scope}. Empty value = the tool's own default.")
    else:
        try:
            directory = find_competition(args.dir)
        except GateError:
            directory = None
    for name in names:
        print(f"{name}: {describe_choice(agent_choice(settings, directory, name))}")
    return 0


def refresh_limit(directory):
    """Kaggle can change a competition's daily limit; follow it when the API reports one."""
    from kaggle_agent import kaggle_cli
    from kaggle_agent import submit as submissions
    sub = submissions.settings(directory)
    if not sub["slug"]:
        return
    try:
        limit = kaggle_cli.info(sub["slug"]).get("daily_limit")
    except Exception:
        return
    if limit and int(limit) != sub["daily_limit"]:
        submissions.save_settings(directory, daily_limit=int(limit))
        print(f"Daily submission limit updated from Kaggle: {sub['daily_limit']} -> {limit}")


def run_with_events(run_args, st, on_event):
    """Same as `python -m kaggle_agent start --mode code`, with live events."""
    from kaggle_agent.__main__ import run
    run_args.on_event = on_event
    return run(run_args, st)


# ---------------------------------------------------------------- status / dash / usage / stop
def cmd_status(args, ask):
    import statistics
    from kaggle_agent import submit as submissions
    from kaggle_agent.__main__ import competition_id
    directory = find_competition(args.dir)
    profile = json.loads((directory / ".kaggle-agent" / "profile.json").read_text(encoding="utf-8"))
    st = store()
    competition = competition_id(directory)
    rows = st.rows("SELECT * FROM competitions WHERE id=?", (competition,))
    if not rows:
        print(f"{directory.name}: set up, not started yet. Run: ka go")
        return 0
    comp = rows[0]
    submissions.refresh_scores(st, competition, directory)
    sign = 1 if profile.get("direction") == "maximize" else -1
    full = st.rows("SELECT id,state,metadata,result FROM experiments WHERE competition=? AND fidelity='full' ORDER BY created", (competition,))
    done = [(r, statistics.mean(json.loads(r["result"])["fold_scores"])) for r in full if r["state"] == "COMPLETED" and r["result"]]
    best = max(done, key=lambda item: sign * item[1]) if done else None
    print(f"{directory.name} · {profile['metric']} ({'higher' if sign > 0 else 'lower'} is better) · state {comp['state'].lower()}")
    print(f"Runs: {len(done)} completed, {len(full) - len(done)} failed")
    if best:
        print(f"Best CV: {best[1]:.6g} · {json.loads(best[0]['metadata']).get('hypothesis', '')[:80]} [{best[0]['id'][:8]}]")
    print("Recent:")
    for r, value in done[-5:][::-1]:
        tag = " ← champion" if r["id"] in (comp["champion"], comp["ensemble_champion"]) else ""
        print(f"  {value:.6g}  {json.loads(r['metadata']).get('hypothesis', '')[:70]}{tag}")
    sub = submissions.settings(directory)
    quota = submissions.quota(st, competition, directory)
    print(f"Submissions today: {quota['used_today']}/{quota['limit']} · auto-submit {'on' if sub['auto'] else 'off'}")
    for s in submissions.history(st, competition, 3):
        public = f"public {s['public_score']:.6g}" if s["public_score"] is not None else s["status"]
        print(f"  {s['created'][:16].replace('T', ' ')} cv {s['cv']:.6g} · {public}")
    if profile.get("deadline"):
        from datetime import datetime, timezone
        left = datetime.fromisoformat(profile["deadline"]) - datetime.now(timezone.utc)
        print(f"Deadline in {left.days} days {left.seconds // 3600} h")
        if left.days < 2:
            print("  Final picks: on Kaggle, select your best-CV submission and one different-model hedge.")
    return 0


def cmd_dash(args, ask):
    from kaggle_agent.dashboard import build
    from kaggle_agent.__main__ import competition_id
    directory = find_competition(args.dir)
    profile = json.loads((directory / ".kaggle-agent" / "profile.json").read_text(encoding="utf-8"))
    st = store()
    competition = competition_id(directory)
    if not st.rows("SELECT id FROM competitions WHERE id=?", (competition,)):
        controller_for(directory, st)
    from kaggle_agent import submit as submissions
    submissions.refresh_scores(st, competition, directory)
    path = build(st, competition, directory, profile)
    print(f"Progress page: {path} (refreshes every 30 s while `ka go` runs)")
    if not args.no_open:
        webbrowser.open(path.as_uri())
    return 0


def cmd_usage(args, ask):
    from kaggle_agent.__main__ import usage
    result = usage(store())
    if not result["days"]:
        print("No agent sessions yet.")
    for day, entry in sorted(result["days"].items())[-7:]:
        states = ", ".join(f"{k} {v}" for k, v in entry["states"].items())
        tokens = f" · tokens in {entry['input_tokens']:,} out {entry['output_tokens']:,}" if entry["input_tokens"] else ""
        print(f"{day}: {entry['sessions']} sessions ({states}){tokens}")
    if result["recent_limit_hits"]:
        print("Recent usage-limit stops: " + ", ".join(t[:16] for t in result["recent_limit_hits"]))
    return 0


def cmd_stop(args, ask):
    directory = find_competition(args.dir)
    st = store()
    _, _, controller = controller_for(directory, st)
    controller.request_stop()
    print("Stop requested. A running `ka go` finishes its current step, saves a checkpoint and stops.")
    return 0


# ---------------------------------------------------------------- git history
def cmd_history(args, ask):
    from kaggle_agent import vcs
    directory = find_competition(args.dir)
    entries = vcs.log(directory, args.limit)
    if not entries:
        print("No code history yet. It starts with the first scored run of `ka go` or `register-run`.")
        return 0
    for e in entries:
        tags = f"  [{', '.join(e['tags'])}]" if e["tags"] else ""
        print(f"{e['commit']}  {e['date']}  {e['subject']}{tags}")
    print("\nCompare with the champion: ka diff <run-id>   Get old code back: ka restore <run-id>")
    return 0


def cmd_diff(args, ask):
    from kaggle_agent import vcs
    directory = find_competition(args.dir)
    base = vcs.latest_champion(directory) if not args.against else vcs.find_run(directory, args.against)
    if args.run:
        target = vcs.find_run(directory, args.run)
    else:
        target = vcs.git(directory, "rev-parse", "HEAD").strip()
    text = vcs.diff(directory, base, target)
    print(text if text.strip() else "No code differences.")
    return 0


def cmd_restore(args, ask):
    from kaggle_agent import vcs
    directory = find_competition(args.dir)
    commit = vcs.latest_champion(directory) if args.run == "champion" else vcs.find_run(directory, args.run)
    destination = Path(args.to) if args.to else directory / "restored" / args.run[:8]
    path, count = vcs.restore(directory, commit, destination)
    print(f"Copied {count} file(s) from {args.run} to {path}. Nothing else changed.")
    return 0


# ---------------------------------------------------------------- submit
def cmd_submit(args, ask):
    from kaggle_agent import submit as submissions
    from kaggle_agent import notify
    from kaggle_agent.__main__ import competition_id
    directory = find_competition(args.dir)
    profile = json.loads((directory / ".kaggle-agent" / "profile.json").read_text(encoding="utf-8"))
    if args.auto or args.limit is not None or args.reserve is not None:
        changes = {}
        if args.auto:
            changes["auto"] = args.auto == "on"
        if args.limit is not None:
            if args.limit < 1:
                raise GateError("Daily limit must be at least 1")
            changes["daily_limit"] = args.limit
        if args.reserve is not None:
            changes["reserve"] = max(0, args.reserve)
        value = submissions.save_settings(directory, **changes)
        print(f"{directory.name}: auto-submit {'on' if value['auto'] else 'off'} · daily limit {value['daily_limit']} "
              f"· {value['reserve']} kept for you (auto may use {max(0, value['daily_limit'] - value['reserve'])}).")
        return 0
    st = store()
    competition = competition_id(directory)
    if not st.rows("SELECT id FROM competitions WHERE id=?", (competition,)):
        raise GateError("No runs yet. Run: ka go")
    experiment = None
    if args.run:
        matches = st.rows("SELECT id FROM experiments WHERE competition=? AND id LIKE ?", (competition, args.run + "%"))
        if len(matches) != 1:
            raise GateError("Run id not found or ambiguous; copy it from `ka status`")
        experiment = matches[0]["id"]

    def confirm(path, cv, left):
        if args.yes:
            return True
        print(f"File: {path}\nRun CV: {cv:.6g} · submissions left today: {left['manual_left']}")
        return yes(ask("Submit to Kaggle? (y/n)", "n"))
    result = submissions.submit(st, competition, directory, profile, experiment, confirm=confirm)
    if not result.get("sent"):
        print("Not sent: " + (result.get("reason") or result.get("error") or "unknown"))
        return 1 if result.get("status") == "failed" else 0
    print(f"Submitted {result['experiment'][:8]} (cv {result['cv']:.6g}). Public score appears in `ka status` in a few minutes.")
    notify.send(load_settings(), "Submission", f"{directory.name}: manual {result['experiment'][:8]} cv {result['cv']:.6g}")
    from kaggle_agent.dashboard import build
    build(st, competition, directory, profile)
    return 0


def parser():
    p = argparse.ArgumentParser(prog="ka", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("setup", help="one-time settings")
    new = sub.add_parser("new", help="set up a competition from its Kaggle URL")
    new.add_argument("url")
    new.add_argument("--folder");new.add_argument("--root");new.add_argument("--folds", type=int, default=5)
    new.add_argument("--yes", action="store_true", help="accept detected settings")
    new.add_argument("--no-download", action="store_true", help="data is already in <folder>/data")
    new.add_argument("--optimization", action="store_true");new.add_argument("--scorer");new.add_argument("--solution-name")
    new.add_argument("--direction", choices=["minimize", "maximize"])
    go = sub.add_parser("go", help="run or resume the agent loop")
    go.add_argument("--campaigns", type=int);go.add_argument("--trials", type=int);go.add_argument("--agent", choices=["claude", "codex"])
    for name in ("status", "dash", "stop", "usage"):
        sub.add_parser(name)
    sub.add_parser("research", help="read public notebooks and forum threads now")
    ag = sub.add_parser("agent", help="show or set the model and effort of an agent")
    ag.add_argument("name", nargs="?", choices=["claude", "codex"])
    ag.add_argument("--model", help="model name; empty string = tool default")
    ag.add_argument("--effort", help="low, medium, high, xhigh (claude also max); empty string = tool default")
    ag.add_argument("--global", dest="use_global", action="store_true", help="save for every competition, not just this folder")
    h = sub.add_parser("history", help="code versions of every scored run (git)")
    h.add_argument("--limit", type=int, default=30)
    d = sub.add_parser("diff", help="code changes between the champion and a run")
    d.add_argument("run", nargs="?");d.add_argument("--against", help="compare with this run instead of the champion")
    r = sub.add_parser("restore", help="copy a past run's code into a folder")
    r.add_argument("run", help="run id from `ka history`, or champion");r.add_argument("--to")
    s = sub.add_parser("submit", help="submit the best run now, or turn auto-submit on/off")
    s.add_argument("run", nargs="?");s.add_argument("--auto", choices=["on", "off"]);s.add_argument("--yes", action="store_true")
    s.add_argument("--limit", type=int, help="this competition's daily submission limit");s.add_argument("--reserve", type=int, help="daily slots auto-submit leaves for you")
    for name, command in sub.choices.items():
        command.add_argument("--dir", help="competition folder (default: current folder)")
        if name == "dash":
            command.add_argument("--no-open", action="store_true")
    return p


COMMANDS = dict(setup=cmd_setup, new=cmd_new, go=cmd_go, status=cmd_status, dash=cmd_dash, stop=cmd_stop, usage=cmd_usage, agent=cmd_agent, research=cmd_research,
                submit=cmd_submit, history=cmd_history, diff=cmd_diff, restore=cmd_restore)


def main(argv=None, ask=ask_console):
    args = parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args, ask)
    except KeyboardInterrupt:
        print("\nInterrupted. Progress is saved; run `ka go` to continue.")
        return 130
    except (GateError, ValueError, OSError, RuntimeError) as error:  # GitError is a RuntimeError
        print(f"ka: {friendly(error)}", file=sys.stderr)
        return 2


def friendly(error):
    text = str(error)
    hints = {
        "Data, folds or scorer changed": "Your data files or folds changed since setup. Restore them, or set up a new folder with `ka new`.",
        "Supervisor lease held": "Another `ka go` is already running for this competition.",
        "Competition rules must be reviewed": "Read the rules, then set \"rules_reviewed\": true in .kaggle-agent/profile.json.",
        "Competition deadline passed": "The competition deadline has passed.",
        "missing_binary": "The agent CLI was not found. Install Claude Code or Codex, or run `ka setup`.",
    }
    for key, hint in hints.items():
        if key in text:
            return hint
    return text


if __name__ == "__main__":
    raise SystemExit(main())
