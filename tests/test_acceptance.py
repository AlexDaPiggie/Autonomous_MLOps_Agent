from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import shutil
import unittest
from unittest.mock import patch
import psutil

from kaggle_agent.agents.base import CLIAdapter,AgentResult
from kaggle_agent.execution.gates import GateError,prelaunch,validate_profile
from kaggle_agent.execution.local import LocalProvider
from kaggle_agent.initialize import initialize
from kaggle_agent.storage.database import Store
from kaggle_agent.supervisor.budget import Budget,BudgetError
from kaggle_agent.supervisor.recovery import recovery_action
from kaggle_agent.supervisor.watchdog import run_process
from tests.test_reliability import profile,metadata


class Acceptance(unittest.TestCase):
    @unittest.skipUnless(os.name=="nt","Windows batch wrapper")
    def test_actual_batch_wrapper_with_spaces(self):
        with tempfile.TemporaryDirectory(prefix="batch wrapper ") as temp:
            root=Path(temp);shared=root/"shared tools";package=shared/"kaggle_agent"
            package.mkdir(parents=True)
            repo=Path(__file__).resolve().parents[1]
            shutil.copy2(repo/"new_competition.bat",shared/"new_competition.bat")
            shutil.copy2(repo/"kaggle_agent"/"initialize.py",package/"initialize.py")
            command=f'cmd.exe /d /s /c ""{shared / "new_competition.bat"}" "Competition With Spaces" "https://example.invalid/?a=1&b=2""'
            result=subprocess.run(command,capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn("?a=1&b=2",(root/"Competition With Spaces"/"AGENTS.md").read_text())

    def test_prompt_stdin_and_successful_cli_protocol(self):
        with tempfile.TemporaryDirectory() as temp:
            literal='quotes " and & and $(not-executed)'
            result=run_process([sys.executable,"-c","import sys; print(sys.stdin.read())"],temp,Path(temp)/"stdin.log",input_text=literal)
            self.assertEqual(result["exit_code"],0)
            self.assertIn(literal,(Path(temp)/"stdin.log").read_text())
            adapter=CLIAdapter("codex")
            def fake_run(command,cwd,log_path,**kwargs):
                self.assertNotIn(literal,command)
                self.assertIn(literal,kwargs["input_text"])
                Path(log_path).write_text(json.dumps(dict(type="thread.started",thread_id="mock-thread"))+"\n"+json.dumps(dict(type="turn.completed",usage=dict(input_tokens=7,output_tokens=3))))
                Path(command[command.index("--output-last-message")+1]).write_text(json.dumps(dict(status="completed",session_id=None,experiment_ids=[],checkpoint=None,next_action="review",termination_reason="done")))
                return dict(termination_reason="exit",exit_code=0)
            with patch.object(adapter,"binary",return_value="mock-cli"),patch("kaggle_agent.agents.base.run_process",side_effect=fake_run),patch.dict("os.environ",{},clear=True):
                result=adapter.run(literal,temp,authorized=True)
            self.assertEqual(result.session_id,"mock-thread")
            self.assertEqual(result.usage["input_tokens"],7)
            self.assertIsNotNone(result.checkpoint)

    def test_agent_cli_faults_without_inference(self):
        with tempfile.TemporaryDirectory() as temp:
            for name in ("codex","claude"):
                for output,exit_code,reason in [("not logged in",1,"authentication"),("rate limit reached",1,"usage_limit"),
                                                ("malformed",0,"malformed_output"),("",2,"agent_exit")]:
                    with self.subTest(agent=name,reason=reason):
                        adapter=CLIAdapter(name)
                        def fake_run(command,cwd,log_path,**kwargs):
                            Path(log_path).write_text(output)
                            if name=="codex":Path(command[command.index("--output-last-message")+1]).write_text(output)
                            return dict(termination_reason="exit",exit_code=exit_code)
                        with patch.object(adapter,"binary",return_value="mock-cli"),patch("kaggle_agent.agents.base.run_process",side_effect=fake_run),patch.dict("os.environ",{},clear=True):
                            result=adapter.run("bounded task",temp,authorized=True)
                        self.assertEqual(result.termination_reason,reason)
                with patch.object(CLIAdapter,"binary",return_value=None),patch.dict("os.environ",{},clear=True):
                    self.assertEqual(CLIAdapter(name).run("task",temp,authorized=True).termination_reason,"missing_binary")

    def test_windows_initializer_preserves_existing(self):
        with tempfile.TemporaryDirectory(prefix="initializer space ") as temp:
            shared=Path(temp)/"shared tools";shared.mkdir()
            target=initialize(temp,"Competition With Spaces","https://example.invalid/competition?a=1&b=2",shared=shared,automation=True)
            original=(target/"AGENTS.md").read_text()
            self.assertIn("../shared tools/rules.md",original)
            self.assertIn("@AGENTS.md",(target/"CLAUDE.md").read_text())
            with self.assertRaises(FileExistsError):initialize(temp,target.name,shared=shared)
            self.assertEqual((target/"AGENTS.md").read_text(),original)
            with self.assertRaises(ValueError):initialize(temp,"../escape",shared=shared)
            self.assertFalse(json.loads((target/".kaggle-agent"/"profile.json").read_text())["rules_reviewed"])

    def test_db_process_crash_rolls_back(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"db.sqlite3";store=Store(path)
            code="import sqlite3,sys,os; d=sqlite3.connect(sys.argv[1]); d.execute('BEGIN IMMEDIATE'); d.execute(\"INSERT INTO events(kind,details,created) VALUES('crash','{}','now')\"); os._exit(9)"
            result=subprocess.run([sys.executable,"-c",code,str(path)],timeout=10)
            self.assertEqual(result.returncode,9)
            self.assertFalse(store.rows("SELECT * FROM events"))

    def test_active_local_reconciliation_pid_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);job=root/"job";job.mkdir()
            child=subprocess.Popen([sys.executable,"-c","import time; time.sleep(30)"])
            try:
                state=dict(state="RUNNING",pid=child.pid,process_created=psutil.Process(child.pid).create_time(),job_id="job")
                (job/"status.json").write_text(json.dumps(state))
                provider=LocalProvider(root)
                self.assertEqual(provider.reconcile("job")["state"],"RUNNING")
                with self.assertRaises(GateError):provider.launch("job",{})
                (job/"status.json").write_text(json.dumps(state|dict(process_created=0)))
                self.assertEqual(provider.reconcile("job")["state"],"FAILED")
            finally:
                child.kill();child.wait()

    def test_budget_rollover_stricter_caps_and_billing_facts(self):
        with tempfile.TemporaryDirectory() as temp:
            budget=Budget(Store(Path(temp)/"db.sqlite3"))
            budget.configure(confirmed=True,competition_cents=90,campaign_cents=80)
            config=budget.summary()["config"]
            self.assertEqual(budget.period(config,datetime(2026,12,1,tzinfo=timezone.utc)),"2026-12-01")
            key=budget.reserve("c","a",80,authorized=True)
            budget.reconcile(key,80)
            with self.assertRaises(BudgetError):budget.reserve("c","b",11,authorized=True)
            key=budget.reserve("c","b",10,authorized=True)
            with budget.store.transaction() as db:db.execute("UPDATE costs SET period='2025-01-01' WHERE id=?",(key,))
            self.assertEqual(budget.summary()["committed_cents"],90) # stale uncertain reservation retained
            budget.reconcile(key,15) # record overrun and disable new spending
            self.assertFalse(budget.summary()["config"]["confirmed"])
            with self.assertRaises(BudgetError):budget.configure(confirmed=True,competition_cents=100,campaign_cents=80)
            budget.record_charge(identifier="storage-1",actual_cents=30,kind="storage",period=budget.summary()["period"])
            budget.record_charge(identifier="storage-1",actual_cents=30,kind="storage",period=budget.summary()["period"])
            with self.assertRaises(BudgetError):budget.record_charge(identifier="storage-1",actual_cents=31,kind="storage",period=budget.summary()["period"])
            with self.assertRaises(BudgetError):budget.configure(confirmed="false")

    def test_deadline_stricter_resources_and_bounded_recovery(self):
        expired=profile()|dict(deadline="2020-01-01T00:00:00+00:00")
        with self.assertRaises(GateError):validate_profile(expired)
        validate_profile(expired,check_deadline=False) # still permits status/stop/export
        with self.assertRaises(GateError):prelaunch(profile()|dict(constraints=dict(seconds=5)),metadata(),smoke_passed=True,seconds=6,memory_mb=128,provider="mock")
        self.assertFalse(recovery_action("ambiguous_launch",0)["retry"])
        self.assertEqual(recovery_action("usage_limit",0)["state"],"WAITING_LIMIT")
        self.assertFalse(recovery_action("agent_exit",3)["retry"])
        self.assertTrue(recovery_action("agent_exit",1)["retry"])

    def test_agent_killed_early_exit_recorded(self):
        with tempfile.TemporaryDirectory() as temp:
            killed=False
            def kill(**process):
                nonlocal killed
                if not killed:
                    psutil.Process(process["pid"]).kill();killed=True
            result=run_process([sys.executable,"-c","import time; time.sleep(20)"],temp,Path(temp)/"exit.log",heartbeat=kill)
            self.assertNotEqual(result["exit_code"],0)
            self.assertEqual(result["termination_reason"],"exit")
