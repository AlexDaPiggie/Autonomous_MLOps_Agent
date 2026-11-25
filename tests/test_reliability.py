from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

from kaggle_agent.agents.base import CLIAdapter, validate_result
from kaggle_agent.execution.gates import GateError, acceptance, paid_launch
from kaggle_agent.execution.providers import MockProvider
from kaggle_agent.storage.database import Store, checksum, fingerprint
from kaggle_agent.supervisor.budget import Budget, BudgetError
from kaggle_agent.supervisor.controller import Controller
from kaggle_agent.supervisor.lifecycle import transition
from kaggle_agent.supervisor.watchdog import run_process


def profile():
    return dict(task="regression",metric="rmse",direction="minimize",data_hash="data",split_hash="split",
                rules_reviewed=True,external_resources=[],validation="fixed",deadline=None,baseline=None,constraints={})


def metadata():
    return dict(code_hash="code",config={"x":1},data_hash="data",split_hash="split",seed=42,metric="rmse",evaluator_hash="eval")


class Reliability(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root/"state.sqlite3")
        self.controller = Controller(self.store,"test")
        self.controller.register(self.root,profile())
        self.controller.acquire()

    def tearDown(self):
        self.temp.cleanup()

    def result(self):
        (self.root/"prediction.json").write_text("[1,2,3]")
        return dict(complete=True,evaluator_hash="eval",config_hash=fingerprint({"x":1}),data_hash="data",split_hash="split",
                    fold_scores=[1.,2.],score_type="base_oof",artifacts={"prediction.json":checksum(self.root/"prediction.json")})

    def test_lifecycle_and_duplicate(self):
        campaign = self.controller.campaign()
        provider = MockProvider()
        key = self.controller.launch(campaign,metadata(),provider,smoke_passed=True)
        self.controller.finish(key,self.result(),self.root)
        campaign2 = self.controller.campaign()
        with self.assertRaises(sqlite3.IntegrityError):
            self.controller.launch(campaign2,metadata(),provider,smoke_passed=True)
        self.assertEqual(provider.launches,1)

    def test_lease_and_recovery_no_duplicate(self):
        other = Controller(self.store,"test")
        with self.assertRaises(GateError): other.acquire()
        provider = MockProvider(fault="ambiguous")
        key = self.controller.launch(self.controller.campaign(),metadata(),provider,smoke_passed=True)
        self.controller.release()
        other.acquire()
        other.reconcile(provider)
        self.assertEqual(provider.launches,1)
        self.assertEqual(self.store.rows("SELECT state FROM remote_jobs WHERE key=?",(key,))[0]["state"],"RUNNING")
        with self.assertRaises(GateError): other.campaign()

    def test_unknown_launch_blocks(self):
        provider = MockProvider()
        self.controller.launch(self.controller.campaign(),metadata(),provider,smoke_passed=True)
        provider.fault="unreconcilable"
        self.controller.reconcile(provider)
        self.assertEqual(self.store.rows("SELECT state FROM competitions")[0]["state"],"BLOCKED")

    def test_gates_and_stop(self):
        with self.assertRaises(GateError): paid_launch()
        with self.assertRaises(ValueError): transition(self.store,"test","COMPLETED","skip")
        self.controller.request_stop()
        with self.assertRaises(GateError): self.controller.campaign()
        self.controller.campaign(resume=True)
        value = self.result()
        value["fold_scores"]=[float("nan")]
        with self.assertRaises(GateError): acceptance(value,metadata(),self.root)
        value=self.result(); value["evaluator_hash"]="tampered"
        with self.assertRaises(GateError): acceptance(value,metadata(),self.root)

    def test_atomic_rollback(self):
        with self.assertRaises(RuntimeError):
            with self.store.transaction() as db:
                self.store.event("rolled_back",{},db=db)
                raise RuntimeError()
        self.assertFalse(self.store.rows("SELECT * FROM events WHERE kind='rolled_back'"))

    def test_budget_concurrent_and_uncertain(self):
        budget=Budget(self.store)
        with self.assertRaises(BudgetError): budget.reserve("test","a",100,authorized=True)
        budget.configure(confirmed=True,fixed_cents=3400,reserve_cents=500)
        def reserve(i):
            try:return budget.reserve("test",str(i),100,authorized=True)
            except BudgetError:return None
        with ThreadPoolExecutor(max_workers=8) as pool:
            keys=list(pool.map(reserve,range(8)))
        self.assertEqual(sum(k is not None for k in keys),1)
        key=next(k for k in keys if k)
        budget.reconcile(key)
        self.assertEqual(budget.summary()["available_cents"],0)
        with self.assertRaises(BudgetError): budget.reserve("test","b",1,authorized=True)
        budget.reconcile(key,25)
        self.assertEqual(budget.summary()["available_cents"],75)
        with self.assertRaises(BudgetError): budget.reserve("test","b",1,authorized=True,pricing_known=False)

    def test_watchdog_timeout_exit_stop(self):
        for code, kwargs, reason in [("import time; time.sleep(5)",dict(seconds=.15),"timeout"),
                                     ("raise SystemExit(2)",{},"exit"),
                                     ("import time; time.sleep(5)",dict(should_stop=lambda:True),"user_stop")]:
            result=run_process([sys.executable,"-c",code],self.root,self.root/"out.log",**kwargs)
            self.assertEqual(result["termination_reason"],reason)
            self.assertNotEqual(result["exit_code"],0)

    def test_agent_disabled_and_protocol(self):
        self.assertEqual(CLIAdapter("codex").run("task",self.root).status,"blocked")
        with self.assertRaises(ValueError): validate_result({"status":"completed"})
