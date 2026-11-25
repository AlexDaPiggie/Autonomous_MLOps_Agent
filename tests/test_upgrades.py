"""Second upgrade round: real tables, referee, code-writing loop, optimization plugin,
limits, blending, portfolio and adapter fixes. Mock agents and synthetic data only."""
import argparse
from contextlib import redirect_stdout, redirect_stderr
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from kaggle_agent.__main__ import main, run
from kaggle_agent.agents.base import CLIAdapter, MockCoder, extract_json
from kaggle_agent.execution.gates import GateError, validate_config
from kaggle_agent.storage.database import Store

ROOT = Path(__file__).resolve().parents[1]

BASELINE = '''
import numpy as np
from sklearn.linear_model import LogisticRegression
from kaggle_agent import toolkit as kt
d = kt.load()
from pandas.api.types import is_numeric_dtype
cols = [c for c in kt.features(d) if is_numeric_dtype(d["train"][c])]
X, T, y = d["train"][cols].to_numpy(), d["test"][cols].to_numpy(), d["y"]
oof, test = np.zeros((len(y), 2)), np.zeros((len(T), 2))
splits = list(kt.splits(d))
for fold, tr, va in splits:
    m = LogisticRegression(max_iter=500).fit(X[tr], y[tr])
    oof[va] = m.predict_proba(X[va]); test += m.predict_proba(T) / len(splits)
kt.save(d, oof, test, notes={"model": "logistic"})
'''

IMPROVED = '''
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from kaggle_agent import toolkit as kt
d = kt.load()
def feats(f):
    out = f[["x1", "x2", "x3"]].copy()
    out["x1x2"] = f["x1"] * f["x2"]
    out["cat"] = f["cat"].map({"a": 0, "b": 1, "c": 2}).fillna(-1)
    return out.to_numpy()
X, T, y = feats(d["train"]), feats(d["test"]), d["y"]
oof, test = np.zeros((len(y), 2)), np.zeros((len(T), 2))
splits = list(kt.splits(d))
iters = 20 if d["smoke"] else 150
for fold, tr, va in splits:
    m = HistGradientBoostingClassifier(max_iter=iters, learning_rate=.05, max_leaf_nodes=8, min_samples_leaf=30,
                                       random_state=d["seed"]).fit(X[tr], y[tr])
    oof[va] = m.predict_proba(X[va]); test += m.predict_proba(T) / len(splits)
kt.save(d, oof, test, notes={"model": "hist + x1*x2 + category code"})
'''

BROKEN = IMPROVED.replace('out["x1x2"] = f["x1"] * f["x2"]', 'out["x1x2"] = f["x1"] * f["missing_column"]').replace("150", "151")
FIXED = IMPROVED.replace("150", "151")
FORBIDDEN = BASELINE + "\nimport os\nos.system('kaggle competitions submit -c x -f sub.csv -m y')\n"


def make_tables(root, n=1500):
    import numpy as np
    import pandas as pd
    rng = np.random.default_rng(0)
    def frame(rows, prefix):
        x1, x2, x3 = rng.normal(size=(3, rows))
        cat = rng.choice(["a", "b", "c"], rows)
        logit = 2.5 * x1 * x2 + np.sin(2 * x3) + (cat == "b") * 1.0
        y = np.where(rng.random(rows) < 1 / (1 + np.exp(-logit)), "yes", "no")
        return pd.DataFrame({"id": [f"{prefix}{i}" for i in range(rows)], "x1": x1, "x2": x2, "x3": x3, "cat": cat, "y": y})
    data = Path(root) / "data"
    data.mkdir()
    frame(n, "r").to_csv(data / "train.csv", index=False)
    frame(300, "t").drop(columns="y").to_csv(data / "test.csv", index=False)


KNAPSACK_SCORER = '''
import json, pathlib
def score(solution_path, data_dir):
    inst = json.loads((pathlib.Path(data_dir) / "data" / "items.json").read_text())
    pick = [int(x) for x in pathlib.Path(solution_path).read_text().split()]
    assert len(pick) == len(inst["w"]) and set(pick) <= {0, 1}, "malformed"
    assert sum(p * w for p, w in zip(pick, inst["w"])) <= inst["cap"], "infeasible"
    return float(sum(p * v for p, v in zip(pick, inst["v"])))
'''

SOLVER = '''
import json
from kaggle_agent import toolkit as kt
o = kt.optimization()
inst = json.loads((o["data_dir"] / "data" / "items.json").read_text())
order = sorted(range(len(inst["w"])), key=lambda i: {KEY}, reverse=True)
pick, room = [0] * len(inst["w"]), inst["cap"]
for i in order:
    if inst["w"][i] <= room: pick[i], room = 1, room - inst["w"][i]
o["solution"].write_text(" ".join(map(str, pick)))
'''


class Upgrades(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="kaggle upgrades ")
        self.root = Path(self.temp.name)
        self.db = self.root / "global.sqlite3"
        os.environ["KAGGLE_AGENT_HOME"] = str(self.root / "home")

    def tearDown(self):
        self.temp.cleanup()

    def invoke(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["--db", str(self.db), *args])
        return code, json.loads(out.getvalue() if code == 0 else err.getvalue())

    def competition(self, name="comp"):
        directory = self.root / name
        directory.mkdir()
        make_tables(directory)
        code, result = self.invoke("init", "--competition", str(directory), "--task", "classification",
                                   "--train", str(directory / "data/train.csv"), "--test", str(directory / "data/test.csv"),
                                   "--target", "y", "--id", "id", "--metric", "log_loss", "--folds", "4")
        self.assertEqual(code, 0, result)
        path = directory / ".kaggle-agent/profile.json"
        profile = json.loads(path.read_text())
        profile["rules_reviewed"] = True
        path.write_text(json.dumps(profile))
        return directory, profile

    def code_args(self, directory, agent, trials=4, campaigns=1):
        return argparse.Namespace(competition=str(directory), agent="mock", mode="code", execute=True, subscription_confirmed=False,
                                  campaigns=campaigns, trials=trials, seconds=None, memory_mb=None, config=None,
                                  command="start", mock_agent=agent)

    def test_code_agent_uses_configured_memory_instead_of_watchdog_default(self):
        from inspect import signature
        from kaggle_agent.supervisor.watchdog import run_process
        from kaggle_agent.supervisor.limits import Limits
        directory, profile = self.competition()
        profile["constraints"] = dict(memory_mb=1536)
        (directory / ".kaggle-agent/profile.json").write_text(json.dumps(profile))
        store = Store(self.db)
        Limits(store).configure(memory_mb=2048)
        adapter = CLIAdapter("codex")
        observed = []
        def fake_process(command, cwd, log_path, **kwargs):
            cap = kwargs.get("memory_mb", signature(run_process).parameters["memory_mb"].default)
            observed.append(cap)
            Path(log_path).write_text("")
            # A CLI startup above the old hidden 1 GiB cap, below profile/config caps.
            if cap < 1100:
                return dict(termination_reason="memory_limit", exit_code=1)
            Path(command[command.index("--output-last-message") + 1]).write_text(json.dumps(dict(
                status="stopped", session_id=None, experiment_ids=[], checkpoint=None,
                next_action="test complete", termination_reason="user_stop")))
            return dict(termination_reason="exit", exit_code=0)
        with patch.object(adapter, "binary", return_value="mock-cli"), patch(
                "kaggle_agent.agents.base.run_process", side_effect=fake_process):
            result = run(self.code_args(directory, adapter, trials=1), store)
            limited = adapter.run("test lower cap", directory, authorized=True, memory_mb=512)
        self.assertEqual(result["reason"], "user_stop", result)
        self.assertEqual(observed, [1536, 512])
        self.assertEqual(limited.termination_reason, "memory_limit")
        outcome = json.loads((Path(limited.checkpoint) / "outcome.json").read_text())
        self.assertEqual(outcome["memory_mb"], 512)
        self.assertEqual(outcome["termination_reason"], "memory_limit")

    def test_init_real_tables_freezes_folds_and_classes(self):
        directory, profile = self.competition()
        self.assertEqual(profile["data"]["classes"], ["no", "yes"])
        folds = (directory / ".kaggle-agent/folds.csv").read_text().splitlines()
        self.assertEqual(folds[0], "id,fold")
        self.assertEqual(len(folds), 1501)
        # Changing train after freezing is detected before any run.
        with open(directory / "data/train.csv", "a") as f:
            f.write("r9999,0,0,0,a,no\n")
        args = self.code_args(directory, MockCoder([("x", BASELINE)]))
        with self.assertRaises(GateError):
            run(args, Store(self.db))

    def test_propose_mode_on_real_tables(self):
        directory, _ = self.competition()
        code, result = self.invoke("start", "--competition", str(directory), "--execute", "--trials", "2")
        self.assertEqual(code, 0, result)
        self.assertEqual(result["state"], "COMPLETED")
        store = Store(self.db)
        full = store.rows("SELECT * FROM experiments WHERE fidelity='full' AND state='COMPLETED'")
        self.assertGreaterEqual(len(full), 2)
        self.assertTrue(any(json.loads(r["result"]).get("independently_scored") for r in full))
        self.assertTrue(store.rows("SELECT champion FROM competitions")[0]["champion"])

    def test_register_run_scores_independently_and_rejects_duplicates(self):
        directory, profile = self.competition()
        script = directory / "manual.py"
        script.write_text(BASELINE)
        out = directory / "manual_out"
        out.mkdir()
        env = os.environ | dict(KA_DATA_SPEC=json.dumps(profile["data"]), KA_DATA_ROOT=str(directory), KA_TASK="classification",
                                KA_METRIC="log_loss", KA_OUT=str(out), PYTHONPATH=str(ROOT))
        import subprocess
        subprocess.run([sys.executable, str(script)], check=True, env=env, cwd=directory)
        args = ("register-run", "--competition", str(directory), "--oof", str(out / "oof.csv"), "--test", str(out / "test.csv"),
                "--code", str(script), "--hypothesis", "manual logistic")
        code, result = self.invoke(*args)
        self.assertEqual(code, 0, result)
        self.assertTrue(result["promotion"]["improved"])
        self.assertEqual(len(result["fold_scores"]), 4)
        import shutil
        if shutil.which("git"):  # registered code is committed at its real path and tagged
            from kaggle_agent import vcs
            self.assertTrue(result["git_commit"])
            self.assertIn("manual.py", vcs.git(directory, "ls-files"))
            self.assertIn("champion-001", vcs.git(directory, "tag"))
        code, result = self.invoke(*args)
        self.assertEqual(code, 2)
        self.assertIn("Duplicate", result["reason"])
        # A bad OOF (dropped rows) is rejected by the independent evaluator.
        lines = (out / "oof.csv").read_text().splitlines()
        (out / "oof.csv").write_text("\n".join(lines[:-10]) + "\n")
        script.write_text(BASELINE + "\n# changed\n")
        code, result = self.invoke(*args)
        self.assertEqual(code, 2)
        self.assertIn("OOF", result["reason"])

    def test_slow_research_keeps_the_lease_alive(self):
        from unittest.mock import patch
        import time
        from kaggle_agent import loop, submit
        from kaggle_agent.research import public
        from kaggle_agent.supervisor.controller import Controller
        directory, _ = self.competition()
        submit.save_settings(directory, slug="demo-comp")
        beats = []
        original = Controller.heartbeat
        during = []
        def slow(*a, **k):
            start = len(beats)
            time.sleep(0.4)
            during.append(len(beats) - start)
            return dict(errors=[])
        def counting(self, **k):
            beats.append(1)
            return original(self, **k)
        store = Store(self.db)
        with patch.object(public, "refresh", slow), patch.object(loop, "RESEARCH_HEARTBEAT", 0.05), patch.object(Controller, "heartbeat", counting):
            run(self.code_args(directory, MockCoder([("baseline logistic", BASELINE)]), trials=1), store)
        self.assertGreaterEqual(during[0], 4)     # lease renewed while research was running

    def test_resume_after_interrupted_run(self):
        directory, _ = self.competition()
        store = Store(self.db)
        run(self.code_args(directory, MockCoder([("baseline logistic", BASELINE)]), trials=1), store)
        comp = store.rows("SELECT id FROM competitions")[0]["id"]
        # Simulate Ctrl+C in the middle of a run: competition and one experiment stuck in RUNNING.
        with store.transaction() as db:
            db.execute("UPDATE competitions SET state='RUNNING' WHERE id=?", (comp,))
            db.execute("UPDATE experiments SET state='RUNNING' WHERE id=(SELECT id FROM experiments LIMIT 1)")
        args = self.code_args(directory, MockCoder([("hist with interaction feature", IMPROVED)]), trials=1)
        args.command = "resume"
        result = run(args, store)
        self.assertNotEqual(result.get("state"), "BLOCKED", result)
        self.assertTrue(store.rows("SELECT id FROM experiments WHERE state='FAILED' AND failure_reason LIKE 'interrupted%'"))

    def test_code_mode_loop_end_to_end(self):
        directory, _ = self.competition()
        agent = MockCoder([("baseline logistic", BASELINE), ("hist with interaction feature", IMPROVED),
                           ("same idea, broken first", BROKEN, FIXED), ("tries to submit", FORBIDDEN)])
        store = Store(self.db)
        result = run(self.code_args(directory, agent), store)
        outcomes = [n.get("outcome") for n in result["notes"] if "outcome" in n]
        self.assertEqual(outcomes[0], "champion")
        self.assertEqual(outcomes[1], "champion")          # hist beats logistic
        self.assertIn(outcomes[2], {"no improvement", "champion"})  # repaired after smoke failure
        self.assertEqual(outcomes[3], "smoke failed")      # submission blocked by static check
        self.assertTrue(any(p.startswith("REPAIR") for p in agent.prompts))
        champion = store.rows("SELECT champion FROM competitions")[0]["champion"]
        hypothesis = json.loads(store.rows("SELECT metadata FROM experiments WHERE id=?", (champion,))[0]["metadata"])["hypothesis"]
        self.assertIn(hypothesis, {"hist with interaction feature", "same idea, broken first"})
        # Screen stages ran and are linked as parents of full runs.
        self.assertTrue(store.rows("SELECT id FROM experiments WHERE fidelity='screen'"))
        self.assertTrue(store.rows("SELECT id FROM experiments WHERE fidelity='full' AND parent IS NOT NULL"))
        # Lessons were stored and reached a later brief, with results and the branch.
        self.assertTrue(store.rows("SELECT id FROM discoveries"))
        briefs = [p for p in agent.prompts if not p.startswith("REPAIR")]
        self.assertIn("Results so far", briefs[-1])
        self.assertIn("hist with interaction feature", briefs[-1])  # earlier result is shown
        self.assertIn("Branch to pursue", briefs[-1])
        # Ensemble was assessed on registered OOF files.
        self.assertTrue(any("ensemble" in n for n in result["notes"]))
        # The agent's own test environment runs its script in smoke mode inside the workspace.
        import subprocess
        extra = agent.last_kwargs["env_extra"]
        self.assertEqual(str(extra["KA_SMOKE"]), "1")
        workspace = Path(agent.last_kwargs["directory"])
        (workspace / "train.py").write_text(IMPROVED)
        env = os.environ | {k: str(v) for k, v in extra.items()}
        subprocess.run([sys.executable, "train.py"], cwd=workspace, env=env, check=True)
        self.assertTrue((workspace / "_out/oof.csv").is_file())
        from kaggle_agent.execution.script import code_hash
        before = code_hash(workspace)
        (workspace / "_out/notes.json").write_text("{}")
        self.assertEqual(before, code_hash(workspace))        # test output never changes the code fingerprint
        # The champion's code is kept next to its outputs.
        self.assertTrue((directory / ".kaggle-agent/jobs" / champion / "code/train.py").is_file())

    def test_optimization_plugin_and_best_vault(self):
        directory = self.root / "opt"
        (directory / "data").mkdir(parents=True)
        (directory / "data/items.json").write_text(json.dumps(dict(w=[5, 4, 6, 3, 7, 2], v=[10, 40, 30, 50, 35, 8], cap=12)))
        scorer = self.root / "scorer.py"
        scorer.write_text(KNAPSACK_SCORER)
        code, result = self.invoke("init", "--competition", str(directory), "--task", "optimization", "--scorer", str(scorer),
                                   "--files", "data/items.json", "--solution-name", "solution.txt", "--direction", "maximize")
        self.assertEqual(code, 0, result)
        path = directory / ".kaggle-agent/profile.json"
        profile = json.loads(path.read_text())
        profile["rules_reviewed"] = True
        path.write_text(json.dumps(profile))
        by_weight = SOLVER.replace("{KEY}", "-inst['w'][i]")          # light items first
        by_ratio = SOLVER.replace("{KEY}", "inst['v'][i]/inst['w'][i]")  # value density
        infeasible = SOLVER.replace("{KEY}", "1").replace("if inst[\"w\"][i] <= room: ", "if True: ")
        agent = MockCoder([("light first", by_weight), ("value density", by_ratio), ("ignore capacity", infeasible)], entry="solve.py")
        store = Store(self.db)
        result = run(self.code_args(directory, agent, trials=3), store)
        outcomes = [n["outcome"] for n in result["notes"]]
        self.assertEqual(outcomes[2], "smoke failed")
        self.assertIn("Official scoring", agent.prompts[0])      # the brief carries the frozen scorer
        self.assertIn("def score(solution_path, data_dir)", agent.prompts[0])
        best = directory / ".kaggle-agent/best/solution.txt"
        self.assertTrue(best.is_file())
        champion = store.rows("SELECT champion FROM competitions")[0]["champion"]
        score = json.loads(store.rows("SELECT result FROM experiments WHERE id=?", (champion,))[0]["result"])["fold_scores"][0]
        self.assertEqual(score, max(n.get("mean", 0) for n in result["notes"]))
        # Changing the scorer is detected.
        (directory / ".kaggle-agent/scorer.py").write_text(KNAPSACK_SCORER + "\n# edited\n")
        with self.assertRaises(GateError):
            run(self.code_args(directory, MockCoder([("x", by_ratio)], entry="solve.py")), store)

    def test_time_folds_forecast_style_registration(self):
        import numpy as np
        import pandas as pd
        import subprocess
        directory = self.root / "ts"
        (directory / "data").mkdir(parents=True)
        t = np.arange(400)
        frame = pd.DataFrame({"id": [f"d{i}" for i in t], "t": t, "lag": np.sin(t / 7), "y": np.sin((t + 1) / 7) + t * .01})
        frame.to_csv(directory / "data/train.csv", index=False)
        frame.drop(columns="y").assign(id=[f"x{i}" for i in t]).head(50).to_csv(directory / "data/test.csv", index=False)
        code, result = self.invoke("init", "--competition", str(directory), "--task", "forecasting", "--train", str(directory / "data/train.csv"),
                                   "--test", str(directory / "data/test.csv"), "--target", "y", "--time", "t", "--folds", "4")
        self.assertEqual(code, 0, result)
        path = directory / ".kaggle-agent/profile.json"
        profile = json.loads(path.read_text())
        self.assertEqual(profile["data"]["fold_scheme"], "time")
        profile["rules_reviewed"] = True
        path.write_text(json.dumps(profile))
        script = directory / "ridge.py"
        script.write_text('''
import numpy as np
from sklearn.linear_model import Ridge
from kaggle_agent import toolkit as kt
d = kt.load()
cols = ["t", "lag"]
X, T, y = d["train"][cols].to_numpy(), d["test"][cols].to_numpy(), d["y"]
oof = np.zeros(len(y))
for fold, tr, va in kt.splits(d):
    assert d["train"]["t"].to_numpy()[tr].max() < d["train"]["t"].to_numpy()[va].min()  # no future rows
    oof[va] = Ridge().fit(X[tr], y[tr]).predict(X[va])
kt.save(d, oof, Ridge().fit(X, y).predict(T))
''')
        out = directory / "out"
        out.mkdir()
        env = os.environ | dict(KA_DATA_SPEC=json.dumps(profile["data"]), KA_DATA_ROOT=str(directory), KA_TASK="regression",
                                KA_METRIC="rmse", KA_OUT=str(out), PYTHONPATH=str(ROOT))
        subprocess.run([sys.executable, str(script)], check=True, env=env, cwd=directory)
        code, result = self.invoke("register-run", "--competition", str(directory), "--oof", str(out / "oof.csv"),
                                   "--test", str(out / "test.csv"), "--code", str(script))
        self.assertEqual(code, 0, result)
        self.assertEqual(len(result["fold_scores"]), 4)

    def test_limits_are_configurable_within_ceilings(self):
        cfg = self.root / "limits.json"
        cfg.write_text(json.dumps(dict(seconds=7200, max_iterations=5000)))
        code, result = self.invoke("limits", "--configure", str(cfg))
        self.assertEqual(code, 0, result)
        self.assertEqual(result["limits"]["seconds"], 7200)
        cfg.write_text(json.dumps(dict(seconds=10**7)))
        code, result = self.invoke("limits", "--configure", str(cfg))
        self.assertEqual(code, 2)
        cfg.write_text(json.dumps(dict(memory_mb=10**9)))
        code, result = self.invoke("limits", "--configure", str(cfg))
        self.assertEqual(code, 2)
        validate_config("classification", dict(family="lightgbm", parameters=dict(iterations=4000, learning_rate=.02, num_leaves=63)), max_iterations=5000)
        with self.assertRaises(GateError):
            validate_config("classification", dict(family="lightgbm", parameters=dict(iterations=4000)))
        with self.assertRaises(GateError):
            validate_config("classification", dict(family="linear", parameters=dict(num_leaves=3)))

    def test_seeds_full_refit_and_hill_climb(self):
        import numpy as np
        from kaggle_agent.benchmarks import synthetic
        from kaggle_agent.pipelines.tabular import cv_predict
        from kaggle_agent.evaluation.ensemble import conditional_hill_climb, hill_climb_weights
        data = synthetic("regression", 3)
        one = cv_predict(data["X"], data["y"], data["folds"], data["test_X"], task="regression", family="hist", parameters=dict(iterations=20))
        many = cv_predict(data["X"], data["y"], data["folds"], data["test_X"], task="regression", family="hist", parameters=dict(iterations=20), seeds=3, full_refit=True)
        self.assertEqual(len(one["oof"]), len(many["oof"]))
        self.assertNotEqual(one["test"], many["test"])
        y = np.asarray(data["y"])
        good, noise = y + np.random.default_rng(0).normal(0, 1, len(y)), np.random.default_rng(1).normal(0, 50, len(y))
        weights = hill_climb_weights([good, noise], y, "rmse", "minimize")
        self.assertGreater(weights[0], weights[1])
        honest = conditional_hill_climb([good, noise], y, data["folds"], "rmse", "minimize")
        self.assertEqual(len(honest["fold_scores"]), len(set(data["folds"])))

    def test_portfolio_uses_results_and_parks(self):
        from kaggle_agent.research.branches import Portfolio
        from kaggle_agent.supervisor.controller import Controller
        store = Store(self.db)
        with store.transaction() as db:
            db.execute("INSERT INTO competitions(id,path,profile,profile_hash) VALUES('c','p','{}','h')")
        portfolio = Portfolio(store, "c")
        winner, loser = portfolio.add("winner", "works"), portfolio.add("loser", "does not")
        for _ in range(3):
            portfolio.update(winner, improved=True)
        for _ in range(4):
            portfolio.update(loser, improved=False)
        ranked = portfolio.rank(turn=0)
        self.assertEqual(ranked[0]["id"], winner)
        statuses = {r["id"]: r["status"] for r in store.rows("SELECT id,status FROM research_branches")}
        self.assertEqual(statuses[loser], "parked")
        self.assertIn(loser, [r["id"] for r in portfolio.rank(turn=3)])  # exploration still revisits

    def test_agent_environment_hides_api_keys_instead_of_blocking(self):
        from kaggle_agent.agents.base import agent_environment
        saved = dict(os.environ)
        try:
            os.environ.update(OPENAI_API_KEY="x", GEMINI_API_KEY="y", ANTHROPIC_BASE_URL="z", ANTHROPIC_AUTH_TOKEN="t", PATH_KEEP="ok")
            env = agent_environment()
            for name in ("OPENAI_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN"):
                self.assertNotIn(name, env)
            self.assertEqual(env["PATH_KEEP"], "ok")
            # A fake CLI sees no key and the run is not blocked.
            fake = self.root / "fake_codex.py"
            fake.write_text("import json,os,sys\nsys.stdin.read()\nout=sys.argv[sys.argv.index('--output-last-message')+1]\n"
                            "open(out,'w').write(json.dumps(dict(status='completed',session_id=None,experiment_ids=[],checkpoint=None,"
                            "next_action='x',termination_reason=str(sorted(k for k in os.environ if 'API_KEY' in k)))))\n")
            adapter = CLIAdapter("codex")
            adapter.binary = lambda: sys.executable
            original = adapter.command
            adapter.command = lambda prompt, result_path=None, **kw: [sys.executable, str(fake), "--output-last-message", str(result_path)]
            result = adapter.run("task", self.root, authorized=True, seconds=30)
            self.assertEqual(result.status, "completed")
            self.assertEqual(result.termination_reason, "[]")
        finally:
            os.environ.clear()
            os.environ.update(saved)

    def test_expired_login_is_reported_as_authentication(self):
        fake = self.root / "fake_claude.py"
        fake.write_text("import json,sys\nsys.stdin.read()\nprint(json.dumps(dict(type='result',is_error=True,result='Failed to authenticate: "
                        "this login reached its time limit and cannot be renewed. Run `claude auth login` to sign in again')))\nsys.exit(1)\n")
        adapter = CLIAdapter("claude")
        adapter.binary = lambda: sys.executable
        adapter.command = lambda prompt, result_path=None, **kw: [sys.executable, str(fake)]
        result = adapter.run("task", self.root, authorized=True, seconds=30)
        self.assertEqual((result.status, result.termination_reason), ("blocked", "authentication"))

    def test_protocol_is_lenient_on_optional_fields(self):
        from kaggle_agent.agents.base import validate_result
        value = dict(status="completed", session_id=None, experiment_ids=[], checkpoint=None, next_action="x",
                     termination_reason="task_completed", entry="solve.py", hypothesis="h",
                     lessons="one lesson", new_branches=["Use subtraction and division for shorter chains", {"hypothesis": "reuse registers"}])
        result = validate_result(value)
        self.assertEqual(result.entry, "solve.py")
        self.assertEqual(result.lessons, ["one lesson"])
        self.assertEqual([b["hypothesis"] for b in result.new_branches], ["Use subtraction and division for shorter chains", "reuse registers"])
        self.assertIsNone(validate_result(value | dict(entry="../evil.sh")).entry)

    def test_adapter_parsing_and_flags(self):
        self.assertEqual(json.loads(extract_json('Here you go:\n```json\n{"a": 1}\n```')), {"a": 1})
        codex, claude = CLIAdapter("codex"), CLIAdapter("claude")
        codex.binary = lambda: "codex"
        claude.binary = lambda: "claude"
        self.assertIn("workspace-write", codex.command("p", "r", mode="code"))
        self.assertIn("read-only", codex.command("p", "r"))
        self.assertIn("acceptEdits", claude.command("p", mode="code", read_dirs=["/data"]))
        code_cmd = claude.command("p", mode="code")
        self.assertIn("--allowedTools", code_cmd)
        self.assertIn("Bash(python:*)", code_cmd)
        self.assertNotIn("--allowedTools", claude.command("p"))      # propose mode stays read-only
        self.assertIn("--add-dir", claude.command("p", mode="code", read_dirs=["/data"]))
        # A valid answer that mentions "rate limit" is not a usage limit.
        answer = dict(status="completed", session_id=None, experiment_ids=[], checkpoint=None, next_action="x",
                      termination_reason="task_completed", hypothesis="avoid hitting the API rate limit", entry="train.py")
        envelope = json.dumps(dict(result=json.dumps(answer), session_id="s", usage={"input_tokens": 5}))
        parsed = claude.parse(envelope, None)
        self.assertEqual(parsed.status, "completed")
        self.assertEqual(parsed.entry, "train.py")


if __name__ == "__main__":
    unittest.main()
