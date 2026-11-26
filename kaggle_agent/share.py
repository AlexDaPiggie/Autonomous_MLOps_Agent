"""Move a competition between PCs: `ka export`, `ka import`, `ka check`.

The loop's history lives in the global database, keyed by a hash of the folder
path, and some stored values are absolute paths. An export is one zip holding the
folder plus only this competition's rows; an import unpacks it anywhere and
rewrites the ID and paths. Nothing from settings.json or your tokens is copied.
"""
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import uuid
import zipfile

from kaggle_agent.execution.gates import GateError
from kaggle_agent.storage.database import fingerprint, utcnow

FORMAT = 1
SHARED = Path(__file__).resolve().parents[1]

# table -> how to select this competition's rows. Order matters for foreign keys.
TABLES = {
    "competitions": "SELECT * FROM competitions WHERE id=?",
    "campaigns": "SELECT * FROM campaigns WHERE competition=?",
    "research_branches": "SELECT * FROM research_branches WHERE competition=?",
    "experiments": "SELECT * FROM experiments WHERE competition=? ORDER BY rowid",   # parents first
    "predictions": "SELECT p.* FROM predictions p JOIN experiments e ON p.experiment=e.id WHERE e.competition=?",
    "remote_jobs": "SELECT j.* FROM remote_jobs j JOIN experiments e ON j.experiment=e.id WHERE e.competition=?",
    "costs": "SELECT * FROM costs WHERE competition=?",
    "agent_sessions": "SELECT * FROM agent_sessions WHERE competition=?",
    "events": "SELECT * FROM events WHERE competition=? ORDER BY id",
    "discoveries": "SELECT * FROM discoveries WHERE competition=?",
    "knowledge_fts": "SELECT * FROM knowledge_fts WHERE id IN (SELECT id FROM discoveries WHERE competition=?)",
    "submissions": "SELECT * FROM submissions WHERE competition=?",
}

# Scratch space and anything that looks like a credential never goes into the zip.
SKIP_DIRS = {"__pycache__", ".ipynb_checkpoints"}
SKIP_TOP = {(".kaggle-agent", "workspace"), (".kaggle-agent", "smoke")}
SECRET = re.compile(r"(^\.env($|\.))|(^kaggle\.json$)|(^credentials\.json$)|(^access_token$)|(\.(pem|key)$)|(^id_(rsa|ed25519))", re.I)


def path_pattern(root):
    """Match a Windows or POSIX folder path however it was stored: single, JSON-escaped
    (any depth) or forward slashes, any letter case. Longer sibling names do not match."""
    parts = [p for p in re.split(r"[\\/]+", str(root)) if p]
    sep = r"(\\+|/)"
    lead = "/" if str(root).startswith("/") else ""
    return re.compile(lead + sep.join(map(re.escape, parts)) + r"(?![\w.\-])", re.I)


def relocate(text, old, new):
    """Replace folder `old` with `new`, keeping the separator style found in the text."""
    if not isinstance(text, str):
        return text
    parts = [p for p in re.split(r"[\\/]+", str(new)) if p]
    lead = "/" if str(new).startswith("/") else ""

    def swap(match):
        separator = match.group(1) if match.lastindex else os.sep
        return lead + separator.join(parts)

    return path_pattern(old).sub(swap, text)


def _files(directory):
    for folder, dirs, names in os.walk(directory):
        relative = Path(folder).relative_to(directory).parts
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and (*relative, d) not in SKIP_TOP]
        for name in names:
            path = Path(folder) / name
            if name.endswith(".pyc") or SECRET.search(name) or path.is_symlink():
                continue
            yield path, PurePosixPath(*relative, name).as_posix()


def _prepare(store):
    from kaggle_agent import submit
    from kaggle_agent.supervisor.limits import Limits
    submit.ensure(store)
    Limits(store)   # creates its table


def _alive(pid, created):
    import psutil
    try:
        return abs(psutil.Process(pid).create_time() - created) < 1
    except (psutil.Error, TypeError, ValueError):
        return False


def _close_interrupted(tables, directory):
    """A run killed before it could record its end stays 'unfinished' forever. Mark it
    failed in the EXPORTED copy only. Refuse if it is still running, or if it left a
    result that `ka go` can still score."""
    closed = []
    for job in tables["remote_jobs"]:
        if job["state"] not in {"INTENT", "RUNNING", "UNKNOWN"}:
            continue
        folder = directory / ".kaggle-agent" / "jobs" / job["key"]
        try:
            status = json.loads((folder / "status.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            status = {}
        key = job["key"][:8]
        if _alive(status.get("pid", job["pid"]), status.get("process_created", job["process_created"])):
            raise GateError(f"Run {key} is still running. Wait for it to end, then export.")
        if (folder / "result.json").is_file():
            raise GateError(f"Run {key} finished but is not recorded: run `ka go` to score it, `ka stop`, then export.")
        job["state"] = "FAILED"
        for experiment in tables["experiments"]:
            if experiment["id"] == job["experiment"] and experiment["state"] == "RUNNING":
                experiment.update(state="FAILED", failure_reason="interrupted before export")
        closed.append(key)
    return closed


def export(store, directory, destination=None):
    from kaggle_agent.__main__ import competition_id
    from kaggle_agent.evaluation.validation import evaluator_version
    from kaggle_agent.supervisor.limits import Limits
    import time
    directory = Path(directory).resolve()
    competition = competition_id(directory)
    _prepare(store)
    destination = Path(destination or directory.parent / f"{directory.name}-share.zip").resolve()
    if destination.is_relative_to(directory):
        raise GateError("Write the zip outside the competition folder")
    if destination.exists():
        raise GateError(f"{destination} already exists; delete it or pass --out")

    with store.connect() as db:
        db.execute("BEGIN")   # one consistent snapshot of every table
        row = db.execute(TABLES["competitions"], (competition,)).fetchone()
        if not row:
            raise GateError("No history for this folder yet (never run, or the folder was moved)")
        if row["lease_until"] and row["lease_until"] > time.time():
            raise GateError("`ka go` is running. Run `ka stop`, wait until it has finished, then export.")
        tables = {name: [dict(r) for r in db.execute(query, (competition,))] for name, query in TABLES.items()}
    interrupted = _close_interrupted(tables, directory)

    manifest = dict(format=FORMAT, name=directory.name, source_root=str(directory), source_shared=str(SHARED),
                    competition=competition, created=utcnow(), evaluator=evaluator_version(),
                    agent_seconds=Limits(store).get()["agent_seconds"])
    temporary = destination.with_name(destination.name + f".{uuid.uuid4().hex[:8]}.tmp")
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, indent=1))
            archive.writestr("state.json", json.dumps(tables))
            count = 0
            for path, name in _files(directory):
                archive.write(path, "folder/" + name)
                count += 1
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return dict(zip=destination, files=count, runs=len(tables["experiments"]), megabytes=destination.stat().st_size / 1e6,
                interrupted=interrupted)


def _extract(archive, folder):
    for info in archive.infolist():
        if not info.filename.startswith("folder/") or info.is_dir():
            continue
        relative = PurePosixPath(info.filename[len("folder/"):])
        if relative.is_absolute() or any(p == ".." or ":" in p or "\\" in p for p in relative.parts):
            raise GateError(f"Unsafe path in zip: {info.filename}")
        target = folder.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info) as source, target.open("wb") as out:
            shutil.copyfileobj(source, out)


def _rewrite_files(folder, old, new):
    """Job and view records hold absolute paths. Run code is hash-checked: never touched."""
    state = folder / ".kaggle-agent"
    for path in state.rglob("*"):
        if path.suffix not in {".json", ".jsonl"} or not path.is_file() or "code" in path.relative_to(state).parts[:-1]:
            continue
        try:
            text = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            continue
        changed = relocate(text, old, new)
        if changed != text:
            path.write_bytes(changed.encode("utf-8"))


def _columns(db, table):
    return [r[1] for r in db.execute(f"PRAGMA table_info({table})")]


def import_(store, archive_path, target=None, root=None):
    from kaggle_agent.__main__ import competition_id
    from kaggle_agent.evaluation.validation import evaluator_version
    from kaggle_agent.supervisor.limits import Limits
    with zipfile.ZipFile(archive_path) as archive:
        try:
            manifest = json.loads(archive.read("manifest.json"))
            tables = json.loads(archive.read("state.json"))
        except KeyError:
            raise GateError("Not a `ka export` zip")
        if manifest.get("format") != FORMAT:
            raise GateError("This zip comes from a different `ka` version; update _kaggle_shared on both PCs")
        name = manifest["name"]
        if not name or Path(name).name != name or name in {".", ".."}:
            raise GateError("Unsafe folder name in zip")
        target = Path(target).resolve() if target else (Path(root or SHARED.parent) / name).resolve()
        if target.exists():
            raise GateError(f"{target} already exists; nothing was changed. Use --to <new folder>.")
        competition = competition_id(target)
        old_id, old_root = manifest["competition"], manifest["source_root"]
        _prepare(store)
        if store.rows("SELECT id FROM competitions WHERE id=? OR path=?", (competition, str(target))):
            raise GateError("This PC already has history for that folder path. Use --to <another folder>.")

        target.parent.mkdir(parents=True, exist_ok=True)
        staging = target.parent / f".ka-import-{uuid.uuid4().hex[:8]}"
        staging.mkdir()
        try:
            _extract(archive, staging)
            _rewrite_files(staging, old_root, target)

            # The entry file points at rules.md relative to the folder.
            agents = staging / "AGENTS.md"
            if agents.is_file():
                before = os.path.relpath(manifest["source_shared"], old_root).replace("\\", "/") \
                    if Path(manifest["source_shared"]).drive == Path(old_root).drive else None
                try:
                    after = os.path.relpath(SHARED, target).replace("\\", "/")
                except ValueError:   # different drive
                    after = SHARED.as_posix()
                if before:
                    agents.write_bytes(agents.read_bytes().replace(f"{before}/rules.md".encode(), f"{after}/rules.md".encode()))

            # Auto-submit stays off until the new owner turns it on.
            settings = staging / ".kaggle-agent" / "submission.json"
            if settings.is_file():
                value = json.loads(settings.read_text(encoding="utf-8")) | dict(auto=False)
                settings.write_text(json.dumps(value, indent=2), encoding="utf-8")

            def moved(value):
                value = relocate(value, old_root, target)
                return value.replace(old_id, competition) if isinstance(value, str) else value

            os.replace(staging, target)
            try:
                with store.transaction() as db:
                    for table in TABLES:   # fixed names; zip content never becomes SQL
                        columns = _columns(db, table)
                        for row in tables.get(table, []):
                            row = {k: moved(v) for k, v in row.items()}
                            if set(row) - set(columns):
                                raise GateError(f"Unknown columns in {table}; update _kaggle_shared")
                            if table == "competitions":
                                row |= dict(path=str(target), stop_requested=0, lease_owner=None, lease_until=None)
                            if table == "events":
                                row.pop("id", None)
                            if table == "predictions":
                                row["id"] = fingerprint(dict(experiment=row["experiment"], path=row["path"]))
                            names = [c for c in columns if c in row]
                            db.execute(f"INSERT INTO {table}({','.join(names)}) VALUES({','.join('?' * len(names))})",
                                       [row[c] for c in names])
                    store.event("imported", dict(source=old_root, created=manifest["created"]), competition, db)
            except BaseException:
                shutil.rmtree(target, ignore_errors=True)   # our own fresh copy
                raise
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    limits = Limits(store)
    seconds = manifest.get("agent_seconds")
    if type(seconds) is int and seconds > limits.get()["agent_seconds"]:
        limits.configure(agent_seconds=seconds)
    warnings = []
    if manifest.get("evaluator") != evaluator_version():
        warnings.append("_kaggle_shared differs from the exporter's version (scoring code). Copy the same version.")
    return dict(folder=target, runs=len(tables.get("experiments", [])), warnings=warnings)


def check(store, directory, agent_name):
    """(ok, item, how to fix) for everything a resumed loop needs on this PC."""
    from kaggle_agent import kaggle_cli, runs
    from kaggle_agent.agents.base import CLIAdapter
    from kaggle_agent.supervisor.budget import Budget
    from kaggle_agent.supervisor.limits import Limits, memory_ceiling_mb
    directory = Path(directory)
    results = []

    def add(ok, item, fix=""):
        results.append((bool(ok), item, "" if ok else fix))

    add(sys.version_info >= (3, 11), "Python 3.11 or newer", "install Python 3.12")
    add(Budget(store).summary()["config"]["confirmed"], "ka setup done", "run `ka setup`")
    add(Limits(store).get()["memory_mb"] <= memory_ceiling_mb(), "memory limit fits this PC", "run `ka setup`")
    add(CLIAdapter(agent_name).binary(), f"{agent_name} CLI installed", f"install {agent_name} and log in")
    try:
        kaggle_cli.command()
        add(True, "Kaggle CLI installed")
    except Exception:
        add(False, "Kaggle CLI installed", "python -m pip install kaggle")
    config = Path(os.environ.get("KAGGLE_CONFIG_DIR", Path.home() / ".kaggle"))
    add(os.environ.get("KAGGLE_API_TOKEN") or os.environ.get("KAGGLE_KEY")
        or any((config / n).is_file() for n in ("kaggle.json", "access_token", "credentials.json")),
        "Kaggle login found", f"run `kaggle auth login`, or put your own token in {config}")
    code = list((directory / "agent_code").rglob("*.py"))
    if any("g++" in p.read_text(encoding="utf-8", errors="replace") for p in code):
        add(shutil.which("g++") or Path("C:/msys64/ucrt64/bin/g++.exe").is_file(), "g++ compiler (the solver builds C++)",
            "install MSYS2, then its ucrt64 g++")
    try:
        profile = json.loads((directory / ".kaggle-agent" / "profile.json").read_text(encoding="utf-8"))
        frozen = {k: profile[k] for k in ("data_hash", "split_hash")}
        same = not runs.is_real(profile) or runs.identity(directory, profile) == frozen
        add(same, "data, folds and scorer unchanged", "copy the original data files again")
    except Exception as error:
        add(False, "data, folds and scorer unchanged", str(error))
    from kaggle_agent.__main__ import competition_id
    add(store.rows("SELECT id FROM competitions WHERE id=?", (competition_id(directory),)),
        "run history found", "this folder was copied by hand: use `ka export` / `ka import`")
    return results
