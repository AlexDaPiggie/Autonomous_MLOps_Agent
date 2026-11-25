"""Integer-cent ledger; uncertain usage stays reserved across period rollover."""
from calendar import monthrange
from datetime import datetime, timezone
import json
import uuid
from kaggle_agent.storage.database import utcnow


DEFAULTS = dict(monthly_cents=4000, competition_cents=500, campaign_cents=100,
                invocation_cents=100, concurrency=1, reserve_cents=500,
                fixed_cents=0, confirmed=False, billing_day=1)


class BudgetError(ValueError):
    pass


class Budget:
    def __init__(self, store):
        self.store = store

    def configure(self, **settings):
        config = DEFAULTS | settings
        for key in ("monthly_cents", "competition_cents", "campaign_cents", "invocation_cents",
                    "concurrency", "reserve_cents", "fixed_cents", "billing_day"):
            if type(config[key]) is not int or config[key] < 0:
                raise BudgetError(f"Invalid integer setting: {key}")
        if not 1 <= config["billing_day"] <= 28 or not 1 <= config["concurrency"] <= 1:
            raise BudgetError("Billing day must be 1..28 and paid concurrency one")
        if config["monthly_cents"] > 4000 or config["competition_cents"] > 500 or config["campaign_cents"] > 100:
            raise BudgetError("Cannot relax approved default caps")
        with self.store.transaction() as db:
            old = db.execute("SELECT value FROM budget_config WHERE id=1").fetchone()
            if old:
                previous = json.loads(old[0])
                for key in ("monthly_cents", "competition_cents", "campaign_cents", "invocation_cents", "concurrency"):
                    if config[key] > previous[key]:
                        raise BudgetError("Existing stricter cap cannot be relaxed")
            db.execute("INSERT OR REPLACE INTO budget_config VALUES(1,?)", (json.dumps(config),))
            self.store.event("budget_config", config, db=db)

    def config(self, db):
        row = db.execute("SELECT value FROM budget_config WHERE id=1").fetchone()
        return json.loads(row[0]) if row else DEFAULTS.copy()

    def period(self, config, now=None):
        now = now or datetime.now(timezone.utc)
        year, month = now.year, now.month
        if now.day < config["billing_day"]:
            month -= 1
            if month == 0:
                year, month = year - 1, 12
        return f"{year:04d}-{month:02d}-{config['billing_day']:02d}"

    def summary(self):
        with self.store.connect() as db:
            config = self.config(db)
            period = self.period(config)
            used = db.execute("SELECT COALESCE(SUM(CASE WHEN actual IS NULL THEN reserved ELSE actual END),0) FROM costs WHERE period=? OR state IN ('reserved','uncertain')", (period,)).fetchone()[0]
            total = used + config["fixed_cents"]
            return dict(config=config, period=period, committed_cents=total,
                        available_cents=max(0, config["monthly_cents"] - config["reserve_cents"] - total),
                        warnings=[n for n in (50, 75, 90) if total * 100 >= config["monthly_cents"] * n])

    def reserve(self, competition, campaign, maximum_cents, *, pricing_known=True, authorized=False):
        if not authorized or not pricing_known or type(maximum_cents) is not int or maximum_cents <= 0:
            raise BudgetError("Explicit authorization, known price and positive integer maximum required")
        with self.store.transaction() as db:
            config = self.config(db)
            if not config["confirmed"]:
                raise BudgetError("Confirm fixed expenses and UTC billing period first")
            period = self.period(config)
            costs = db.execute("SELECT * FROM costs").fetchall()
            amount = lambda r: r["reserved"] if r["actual"] is None else r["actual"]
            monthly = config["fixed_cents"] + sum(amount(r) for r in costs if r["period"] == period or r["state"] in ("reserved", "uncertain"))
            comp = sum(amount(r) for r in costs if r["competition"] == competition)
            camp = sum(amount(r) for r in costs if r["campaign"] == campaign)
            active = sum(r["state"] in ("reserved", "uncertain") for r in costs)
            if (monthly + maximum_cents + config["reserve_cents"] > config["monthly_cents"]
                    or comp + maximum_cents > config["competition_cents"]
                    or camp + maximum_cents > config["campaign_cents"]
                    or maximum_cents > config["invocation_cents"] or active >= config["concurrency"]):
                raise BudgetError("Budget or concurrency cap reached")
            key = uuid.uuid4().hex
            db.execute("INSERT INTO costs VALUES(?,?,?,?,?,?,?,?,?)",
                       (key, period, competition, campaign, "compute", maximum_cents, None, "reserved", utcnow()))
            return key

    def reconcile(self, key, actual_cents=None):
        if actual_cents is not None and (type(actual_cents) is not int or actual_cents < 0):
            raise BudgetError("Actual cost must be nonnegative integer cents")
        with self.store.transaction() as db:
            row = db.execute("SELECT * FROM costs WHERE id=?", (key,)).fetchone()
            if not row:
                raise BudgetError("Unknown reservation")
            if row["state"] == "settled" and row["actual"] != actual_cents:
                raise BudgetError("Settled charge cannot be silently rewritten")
            db.execute("UPDATE costs SET actual=?,state=? WHERE id=?",
                       (actual_cents, "uncertain" if actual_cents is None else "settled", key))
            self.store.event("cost_reconciled", dict(id=key, actual_cents=actual_cents,
                             overrun=actual_cents is not None and actual_cents > row["reserved"]), db=db)
