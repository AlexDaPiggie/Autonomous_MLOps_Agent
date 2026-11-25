"""Thin wrapper around the official Kaggle CLI (pip install kaggle).

Only the supervisor calls these functions; agent scripts are blocked from
submitting by the static checks in execution/script.py. Set KA_KAGGLE_CLI to a
JSON list (e.g. ["python", "fake_kaggle.py"]) to swap the CLI in tests.
"""
import csv
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import zipfile

from kaggle_agent.execution.gates import require


class KaggleError(RuntimeError):
    pass


def command():
    custom = os.environ.get("KA_KAGGLE_CLI")
    if custom:
        return json.loads(custom)
    binary = shutil.which("kaggle")
    if not binary:
        raise KaggleError("Kaggle CLI not found. Install it with: python -m pip install kaggle "
                          "and put your API token in %USERPROFILE%\\.kaggle\\kaggle.json")
    return [binary]


def run(args, *, timeout=600):
    result = subprocess.run(command() + args, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        text = (result.stderr or result.stdout).strip()
        if "403" in text or "Forbidden" in text or "rules" in text.lower():
            raise KaggleError("Kaggle refused access. Join the competition and accept its rules on the website first.")
        # The "outdated kaggle version" warning is noise: report the real error lines.
        lines = [l for l in text.splitlines() if l.strip() and not l.startswith("Warning:")]
        raise KaggleError(" | ".join(lines[-2:])[:400] if lines else "Kaggle CLI failed")
    return result.stdout


def slug_from(url_or_slug):
    match = re.search(r"kaggle\.com/(?:c|competitions)/([^/?#]+)", url_or_slug)
    slug = match.group(1) if match else url_or_slug.strip().strip("/")
    require(re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug) is not None, f"Not a competition URL or slug: {url_or_slug}")
    return slug


def download(slug, folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    run(["competitions", "download", "-c", slug, "-p", str(folder)], timeout=3600)
    for archive in folder.glob("*.zip"):
        with zipfile.ZipFile(archive) as zipped:
            for member in zipped.namelist():
                target = (folder / member).resolve()
                require(target.is_relative_to(folder.resolve()), "Unsafe path in competition archive")
            zipped.extractall(folder)
    return sorted(p.name for p in folder.iterdir())


def info(slug):
    """Competition facts from the Kaggle API when available (metric, deadline,
    daily submission limit). Returns {} if the API package is unavailable."""
    if os.environ.get("KA_KAGGLE_CLI"):
        path = os.environ.get("KA_KAGGLE_INFO")
        return json.loads(Path(path).read_text()) if path else {}
    try:
        from kaggle.api.kaggle_api_extended import KaggleApi
        api = KaggleApi()
        api.authenticate()
        for comp in api.competitions_list(search=slug) or []:
            ref = str(getattr(comp, "ref", "") or "")
            if ref.rstrip("/").split("/")[-1] == slug:
                get = lambda *names: next((getattr(comp, n) for n in names if getattr(comp, n, None) not in (None, "")), None)
                deadline = get("deadline")
                return dict(metric=get("evaluation_metric", "evaluationMetric"),
                            deadline=deadline.isoformat() if hasattr(deadline, "isoformat") else deadline,
                            daily_limit=get("max_daily_submissions", "maxDailySubmissions", "max_daily_submission_count"),
                            title=get("title"), category=get("category"))
    except Exception:
        return {}
    return {}


def submit(slug, path, message):
    return run(["competitions", "submit", "-c", slug, "-f", str(path), "-m", message], timeout=1800)


def submissions(slug):
    """Past submissions (newest first) as dicts with description, date, status, publicScore."""
    text = run(["competitions", "submissions", "-c", slug, "--csv"], timeout=120)
    lines = [line for line in text.splitlines() if line.strip()]
    start = next((i for i, line in enumerate(lines) if line.lower().startswith(("filename", "ref", "file"))), 0)
    return list(csv.DictReader(io.StringIO("\n".join(lines[start:]))))


METRICS = [  # (pattern in Kaggle's metric name, our metric)
    (r"map\s*@\s*3|mean average precision\s*@?\s*3", "map3"),
    (r"roc|auc|area under", "roc_auc"),
    (r"rmsle|root mean squared log|squared logarithmic", "rmsle"),
    (r"log\s*loss|logarithmic|cross.?entropy|multiclass loss", "log_loss"),
    (r"balanced accuracy", "balanced_accuracy"),
    (r"accuracy", "accuracy"),
    (r"rmse|root mean squared error|root mean square error", "rmse"),
    (r"mape|mean absolute percentage", "mape"),
    (r"\bmae\b|mean absolute error", "mae"),
    (r"\br2\b|r\^2|r-squared|coefficient of determination", "r2"),
]


def map_metric(name):
    if not name:
        return None
    lower = str(name).lower()
    for pattern, metric in METRICS:
        if re.search(pattern, lower):
            return metric
    return None
