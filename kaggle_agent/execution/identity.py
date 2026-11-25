from pathlib import Path
from kaggle_agent.storage.database import checksum,fingerprint


def code_version():
    root=Path(__file__).resolve().parents[1]
    return fingerprint({str(p.relative_to(root)):checksum(p) for p in sorted(root.rglob("*.py"))})
