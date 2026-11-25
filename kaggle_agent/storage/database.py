"""Transactional state. Every connection uses FK enforcement and bounded locking."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False,
                                    separators=(",", ":")).encode()).hexdigest()


def checksum(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY);
INSERT OR IGNORE INTO schema_version VALUES(1);
CREATE TABLE IF NOT EXISTS competitions(
 id TEXT PRIMARY KEY, path TEXT UNIQUE NOT NULL, profile TEXT NOT NULL,
 profile_hash TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'PENDING',
 stop_requested INTEGER NOT NULL DEFAULT 0, lease_owner TEXT, lease_until REAL,
 heartbeat TEXT, champion TEXT, ensemble_champion TEXT);
CREATE TABLE IF NOT EXISTS campaigns(
 id TEXT PRIMARY KEY, competition TEXT NOT NULL REFERENCES competitions(id),
 state TEXT NOT NULL, created TEXT NOT NULL, max_trials INTEGER NOT NULL,
 attempts INTEGER NOT NULL DEFAULT 0, next_action TEXT);
CREATE TABLE IF NOT EXISTS research_branches(
 id TEXT PRIMARY KEY, competition TEXT NOT NULL REFERENCES competitions(id),
 name TEXT NOT NULL, status TEXT NOT NULL, details TEXT NOT NULL, updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS experiments(
 id TEXT PRIMARY KEY, competition TEXT NOT NULL REFERENCES competitions(id),
 campaign TEXT REFERENCES campaigns(id), branch TEXT REFERENCES research_branches(id),
 parent TEXT REFERENCES experiments(id), fingerprint TEXT NOT NULL,
 state TEXT NOT NULL, fidelity TEXT NOT NULL, metadata TEXT NOT NULL,
 result TEXT, failure_reason TEXT, created TEXT NOT NULL,
 UNIQUE(competition, fingerprint));
CREATE TABLE IF NOT EXISTS predictions(
 id TEXT PRIMARY KEY, experiment TEXT NOT NULL REFERENCES experiments(id),
 path TEXT NOT NULL, checksum TEXT NOT NULL, provenance TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS remote_jobs(
 key TEXT PRIMARY KEY, experiment TEXT NOT NULL UNIQUE REFERENCES experiments(id),
 provider TEXT NOT NULL, job_id TEXT, state TEXT NOT NULL, heartbeat TEXT,
 pid INTEGER, process_created REAL, reservation TEXT, details TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS costs(
 id TEXT PRIMARY KEY, period TEXT NOT NULL, competition TEXT, campaign TEXT,
 kind TEXT NOT NULL, reserved INTEGER NOT NULL CHECK(reserved>=0),
 actual INTEGER CHECK(actual>=0), state TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS budget_config(id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS agent_sessions(
 id TEXT PRIMARY KEY, competition TEXT NOT NULL REFERENCES competitions(id),
 agent TEXT NOT NULL, state TEXT NOT NULL, result TEXT, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(
 id INTEGER PRIMARY KEY, competition TEXT, kind TEXT NOT NULL,
 details TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS discoveries(
 id TEXT PRIMARY KEY, competition TEXT, title TEXT NOT NULL, summary TEXT NOT NULL,
 metadata TEXT NOT NULL, created TEXT NOT NULL);
CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(id UNINDEXED,title,summary);
CREATE TABLE IF NOT EXISTS legacy_imports(
 source TEXT NOT NULL, checksum TEXT NOT NULL, content TEXT NOT NULL,
 created TEXT NOT NULL, PRIMARY KEY(source,checksum));
"""


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


class Store:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            existing = db.execute("SELECT name FROM sqlite_master WHERE name='schema_version'").fetchone()
            if existing and db.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] != 1:
                raise ValueError("Unsupported database version; backup and migrate explicitly")
            db.executescript(SCHEMA)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=15, factory=ClosingConnection)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=15000")
        return db

    @contextmanager
    def transaction(self):
        db = self.connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def rows(self, query, args=()):
        with self.connect() as db:
            return [dict(row) for row in db.execute(query, args)]

    def event(self, kind, details, competition=None, db=None):
        args = (competition, kind, json.dumps(details, allow_nan=False), utcnow())
        if db is not None:
            db.execute("INSERT INTO events(competition,kind,details,created) VALUES(?,?,?,?)", args)
        else:
            with self.transaction() as conn:
                conn.execute("INSERT INTO events(competition,kind,details,created) VALUES(?,?,?,?)", args)

    def backup(self, destination):
        with self.connect() as source, sqlite3.connect(destination) as target:
            source.backup(target)
