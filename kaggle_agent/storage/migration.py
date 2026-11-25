"""Archive known legacy formats verbatim; missing provenance is never fabricated."""
import json
from pathlib import Path
from kaggle_agent.storage.database import checksum, utcnow

LEGACY = ("STATE.md", "CONFIG.md", "EXPERIMENTS.md", "EXPERIMENTS_LOG.md",
          "local_leaderboard.md", "prediction_registry.jsonl", "prediction_registry.json")


def migrate(store, directory, *, apply=False):
    directory = Path(directory).resolve()
    report = []
    entries = []
    for name in LEGACY:
        path = directory/name
        if not path.is_file():
            continue
        digest = checksum(path)
        content = path.read_text(encoding="utf-8-sig")
        seen = store.rows("SELECT checksum FROM legacy_imports WHERE source=?", (str(path),))
        status = "unchanged" if any(r["checksum"] == digest for r in seen) else "conflict_preserved" if seen else "new"
        item = dict(source=str(path), checksum=digest, status=status, warnings=[])
        if name.startswith("prediction_registry"):
            try:
                records = ([json.loads(line) for line in content.splitlines() if line.strip()]
                           if name.endswith("jsonl") else json.loads(content))
                if not isinstance(records,list):
                    records = [records]
                item["records"] = len(records)
                item["warnings"].append("Legacy records archived, not eligible for promotion until full provenance is verified")
            except (ValueError,TypeError):
                item["warnings"].append("Malformed registry retained verbatim; manual review required")
        entries.append((str(path),digest,content,utcnow()))
        report.append(item)
    if apply and entries:
        backup = store.path.with_name(store.path.name + ".before-import-" + utcnow().replace(":", "-") + ".bak")
        store.backup(backup)
        with store.transaction() as db:
            db.executemany("INSERT OR IGNORE INTO legacy_imports VALUES(?,?,?,?)", entries)
            store.event("legacy_import", dict(directory=str(directory),report=report,backup=str(backup)),db=db)
    return dict(dry_run=not apply, files=report)
