"""Git history for competition code. The supervisor commits; agents never run git.

Each competition folder gets its own local repository (never pushed). After
every trial that passed its smoke test, the run's exact code is written to
agent_code/ and committed with a message like

    run 3f2a91c4 · roc_auc 0.941200 · NEW CHAMPION · hist + ratio features

Champions are tagged champion-001, champion-002, ... Code you register with
register-run is committed at its real path. Data, predictions and supervisor
files are ignored. If git is missing or a commit fails, the run continues and
the failure is logged: versioning never blocks an experiment.
"""
from pathlib import Path
import re
import shutil
import subprocess

AGENT_DIR = "agent_code"
IGNORE = ["data/", ".kaggle-agent/", "*.zip", "*.parquet", "*.feather", "*.npy", "*.npz", "*.pkl", "*.joblib",
          "*.h5", "*.pt", "*.ckpt", "submission*.csv", "oof*.csv", "catboost_info/", "__pycache__/", "*.pyc",
          ".ipynb_checkpoints/"]


class GitError(RuntimeError):
    pass


def git_binary():
    return shutil.which("git")


def git(directory, *args, check=True):
    binary = git_binary()
    if not binary:
        raise GitError("git is not installed")
    identity = []
    # Use your git identity when you have one; otherwise a local placeholder.
    probe = subprocess.run([binary, "config", "user.name"], cwd=directory, capture_output=True, text=True)
    if not probe.stdout.strip():
        identity = ["-c", "user.name=kaggle-agent", "-c", "user.email=kaggle-agent@localhost"]
    result = subprocess.run([binary, *identity, "-c", "core.autocrlf=true", *args], cwd=directory,
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and result.returncode != 0:
        raise GitError((result.stderr or result.stdout).strip().splitlines()[-1] if (result.stderr or result.stdout).strip() else "git failed")
    return result.stdout


def ensure_repo(directory):
    """Own repository in the competition folder, with a code-only .gitignore."""
    directory = Path(directory)
    if not (directory / ".git").exists():
        git(directory, "init", "-q")
    ignore = directory / ".gitignore"
    lines = ignore.read_text(encoding="utf-8").splitlines() if ignore.is_file() else []
    missing = [p for p in IGNORE if p not in lines]
    if missing:
        header = [] if lines else ["# Code only: data, predictions and supervisor state stay out of git"]
        ignore.write_text("\n".join(lines + header + missing) + "\n", encoding="utf-8")
        git(directory, "add", ".gitignore")
        git(directory, "commit", "-q", "-m", "Track competition code only", "--", ".gitignore", check=False)
    return directory


def _commit(directory, paths, message):
    git(directory, "add", "-A", "--", *paths)
    staged = git(directory, "diff", "--cached", "--name-only", "--", *paths).strip()
    if staged:
        git(directory, "commit", "-q", "-m", message, "--", *paths)
    else:  # same code as last time: record the result anyway
        git(directory, "commit", "-q", "--allow-empty", "-m", message + " (code unchanged)", "--", *paths)
    return git(directory, "rev-parse", "HEAD").strip()


def commit_agent_code(directory, code_dir, message):
    """Replace agent_code/ with this run's code and commit it."""
    directory = Path(directory)
    ensure_repo(directory)
    target = directory / AGENT_DIR
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(code_dir, target, ignore=shutil.ignore_patterns("__pycache__", "champion", "AGENTS.md", "CLAUDE.md"))
    return _commit(directory, [AGENT_DIR], message)


def commit_files(directory, files, message):
    """Commit files registered with register-run at their real paths (inside the folder)."""
    directory = Path(directory).resolve()
    ensure_repo(directory)
    inside = []
    for file in files:
        path = Path(file).resolve()
        if path.is_relative_to(directory):
            inside.append(str(path.relative_to(directory)).replace("\\", "/"))
    if not inside:
        return None
    return _commit(directory, inside, message)


def tag_champion(directory, commit):
    existing = [t for t in git(directory, "tag", "--list", "champion-*").split() if re.fullmatch(r"champion-\d+", t)]
    number = max((int(t.split("-")[1]) for t in existing), default=0) + 1
    name = f"champion-{number:03d}"
    git(directory, "tag", name, commit)
    return name


def message(run_id, metric, mean, outcome, hypothesis):
    return f"run {run_id[:8]} · {metric} {mean:.6f} · {outcome} · {hypothesis[:70]}" if mean is not None else \
           f"run {run_id[:8]} · {outcome} · {hypothesis[:70]}"


def record(store, experiment, commit, tag=None):
    """Keep the commit next to the run's scores."""
    import json
    if not commit or not experiment:
        return
    with store.transaction() as db:
        row = db.execute("SELECT result FROM experiments WHERE id=?", (experiment,)).fetchone()
        if row and row[0]:
            result = json.loads(row[0])
            result["git_commit"] = commit
            if tag:
                result["git_tag"] = tag
            db.execute("UPDATE experiments SET result=? WHERE id=?", (json.dumps(result), experiment))


def safe(store, competition, action, *args, **kwargs):
    """Run a versioning step; on failure log an event and carry on."""
    try:
        return action(*args, **kwargs)
    except Exception as error:
        try:
            store.event("git_skipped", dict(reason=str(error)[:300]), competition)
        except Exception:
            pass
        return None


# ---- reading history ------------------------------------------------------
def log(directory, limit=30):
    if not (Path(directory) / ".git").exists():
        return []
    text = git(directory, "log", f"-{limit}", "--date=format:%Y-%m-%d %H:%M", "--format=%h%x1f%ad%x1f%s%x1f%D", check=False)
    entries = []
    for line in text.splitlines():
        parts = line.split("\x1f")
        if len(parts) == 4:
            tags = [t.replace("tag: ", "") for t in parts[3].split(", ") if t.startswith("tag: ")]
            entries.append(dict(commit=parts[0], date=parts[1], subject=parts[2], tags=tags))
    return entries


def find_run(directory, run_prefix):
    """Commit for a run id prefix (from its commit message)."""
    text = git(directory, "log", "--format=%H", f"--grep=^run {re.escape(run_prefix[:8])}", check=False).split()
    if not text:
        raise GitError(f"No commit for run {run_prefix}; see `ka history`")
    return text[0]


def latest_champion(directory):
    tags = sorted((t for t in git(directory, "tag", "--list", "champion-*").split() if re.fullmatch(r"champion-\d+", t)),
                  key=lambda t: int(t.split("-")[1]))
    if not tags:
        raise GitError("No champion tagged yet")
    return tags[-1]


def diff(directory, base, target):
    return git(directory, "diff", "--stat", "-p", base, target, "--", ".", ":(exclude).gitignore")


def restore(directory, commit, destination):
    """Copy a commit's code (agent_code/ and registered files) into destination."""
    directory, destination = Path(directory), Path(destination)
    if destination.exists() and any(destination.iterdir()):
        raise GitError(f"{destination} is not empty")
    files = [f for f in git(directory, "ls-tree", "-r", "--name-only", commit).splitlines() if f != ".gitignore"]
    for name in files:
        content = subprocess.run([git_binary(), "show", f"{commit}:{name}"], cwd=directory, capture_output=True).stdout
        out = destination / (name[len(AGENT_DIR) + 1:] if name.startswith(AGENT_DIR + "/") else name)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(content)
    return destination, len(files)
