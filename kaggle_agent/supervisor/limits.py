"""User-set resource limits, stored in the global DB.

Defaults keep the original conservative caps. The user may raise them, but
never past the absolute ceilings below (time) or the machine itself
(memory, threads). Every change is logged as an event.
"""
import json
import os

from kaggle_agent.execution.gates import GateError

# Absolute ceilings: no configuration can exceed these.
MAX_SECONDS = 12 * 3600
MAX_ITERATIONS = 100_000


def machine_memory_mb():
    try:
        import psutil
        return int(psutil.virtual_memory().total / 1024**2)
    except Exception:  # pragma: no cover - psutil is a hard dependency
        return 2048


def machine_threads():
    return max(1, os.cpu_count() or 1)


def memory_ceiling_mb():
    """Leave the OS and the agent CLI room: at most 75% of physical RAM."""
    return max(512, int(machine_memory_mb() * 0.75))


DEFAULTS = dict(
    seconds=1800,          # per run
    memory_mb=2048,        # per run (process tree RSS)
    threads=1,             # BLAS/OpenMP/model threads per run
    max_iterations=1000,   # boosting rounds/trees allowed in propose-mode configs
    agent_seconds=900,     # one coding-agent session
    screen_fraction=0.25,  # rows used by the screen stage of script runs
    smoke_rows=2000,       # rows used by the smoke stage
)

SCHEMA = "CREATE TABLE IF NOT EXISTS limits_config(id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL)"


class Limits:
    def __init__(self, store):
        self.store = store
        with store.transaction() as db:
            db.execute(SCHEMA)

    def get(self):
        with self.store.connect() as db:
            row = db.execute("SELECT value FROM limits_config WHERE id=1").fetchone()
        return DEFAULTS | (json.loads(row[0]) if row else {})

    def configure(self, **settings):
        unknown = settings.keys() - DEFAULTS.keys()
        if unknown:
            raise GateError(f"Unknown limit settings: {sorted(unknown)}")
        value = self.get() | settings
        validate(value)
        with self.store.transaction() as db:
            db.execute("INSERT OR REPLACE INTO limits_config VALUES(1,?)", (json.dumps(value),))
            self.store.event("limits_config", value, db=db)
        return value


def validate(value):
    ints = ("seconds", "memory_mb", "threads", "max_iterations", "agent_seconds", "smoke_rows")
    for key in ints:
        if type(value[key]) is not int or value[key] <= 0:
            raise GateError(f"Limit {key} must be a positive integer")
    if value["seconds"] > MAX_SECONDS or value["agent_seconds"] > MAX_SECONDS:
        raise GateError(f"Run and agent time are capped at {MAX_SECONDS} seconds")
    if value["memory_mb"] > memory_ceiling_mb():
        raise GateError(f"Memory limit above 75% of this machine's RAM ({memory_ceiling_mb()} MB)")
    if value["threads"] > machine_threads():
        raise GateError(f"This machine has {machine_threads()} threads")
    if value["max_iterations"] > MAX_ITERATIONS:
        raise GateError(f"Iterations are capped at {MAX_ITERATIONS}")
    fraction = value["screen_fraction"]
    if type(fraction) not in (int, float) or not 0 < fraction <= 1:
        raise GateError("screen_fraction must be in (0, 1]")
    return value


def run_bounds(limits, profile=None):
    """Effective per-run bounds: the user's limits, tightened by the profile."""
    constraints = (profile or {}).get("constraints", {})
    return dict(
        seconds=min(limits["seconds"], constraints.get("seconds", limits["seconds"])),
        memory_mb=min(limits["memory_mb"], constraints.get("memory_mb", limits["memory_mb"])),
        threads=min(limits["threads"], constraints.get("threads", limits["threads"])),
        max_iterations=limits["max_iterations"],
    )
