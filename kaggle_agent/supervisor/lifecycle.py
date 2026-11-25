from enum import StrEnum


class State(StrEnum):
    PENDING = "PENDING"
    IMPLEMENTING = "IMPLEMENTING"
    TESTING = "TESTING"
    RUNNING = "RUNNING"
    EVALUATING = "EVALUATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    WAITING_LIMIT = "WAITING_LIMIT"
    BLOCKED = "BLOCKED"
    STOPPED = "STOPPED"


NEXT = {
    "PENDING": {"IMPLEMENTING", "TESTING"},
    "IMPLEMENTING": {"TESTING"}, "TESTING": {"RUNNING"},
    "RUNNING": {"EVALUATING"}, "EVALUATING": {"COMPLETED"},
    "COMPLETED": {"PENDING"}, "FAILED": {"PENDING"},
    "WAITING_LIMIT": {"PENDING"}, "BLOCKED": {"PENDING"}, "STOPPED": {"PENDING"},
}


def transition(store, competition, target, reason, db=None):
    target = State(target).value
    def update(conn):
        row = conn.execute("SELECT state FROM competitions WHERE id=?", (competition,)).fetchone()
        if row is None:
            raise ValueError("Unknown competition")
        current = row[0]
        if target not in NEXT[current] | {"STOPPED", "FAILED", "BLOCKED", "WAITING_LIMIT"}:
            raise ValueError(f"Illegal transition {current} -> {target}")
        conn.execute("UPDATE competitions SET state=? WHERE id=?", (target, competition))
        store.event("transition", {"from": current, "to": target, "reason": reason}, competition, conn)
    if db is not None:
        update(db)
    else:
        with store.transaction() as conn:
            update(conn)
