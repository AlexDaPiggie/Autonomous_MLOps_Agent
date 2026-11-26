"""`ka` everyday command: setup, new (download + detection), go (live loop +
auto-submit), status, dash, submit, stop. A fake Kaggle CLI records submissions;
no network, no real agent, no money."""
import argparse
from contextlib import redirect_stdout, redirect_stderr
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

from kaggle_agent import ka
from kaggle_agent.agents.base import MockCoder
from kaggle_agent.storage.database import Store
from tests.test_upgrades import BASELINE, IMPROVED, make_tables

FAKE_CLI = r'''
import csv, json, os, sys, zipfile, pathlib
args = sys.argv[1:]
log = pathlib.Path(os.environ["KA_FAKE_LOG"])
if args[:2] == ["competitions", "download"]:
    folder = pathlib.Path(args[args.index("-p") + 1]); folder.mkdir(parents=True, exist_ok=True)
    source = pathlib.Path(os.environ["KA_FAKE_SOURCE"])
    with zipfile.ZipFile(folder / "comp.zip", "w") as z:
        for f in source.iterdir(): z.write(f, f.name)
elif args[:2] == ["competitions", "submit"]:
    entry = dict(file=args[args.index("-f") + 1], message=args[args.index("-m") + 1])
    with log.open("a") as f: f.write(json.dumps(entry) + "\n")
    print("Successfully submitted")
elif args[:2] == ["competitions", "submissions"]:
    rows = [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []
    w = csv.writer(sys.stdout); w.writerow(["fileName", "date", "description", "status", "publicScore"])
    for r in rows: w.writerow([pathlib.Path(r["file"]).name, "2026-11-25", r["message"], "complete", "0.9"])
else:
    sys.exit("unknown command")
'''


def scripted(answers):
    queue = list(answers)
    def ask(question, default=None):
        answer = queue.pop(0) if queue else ""
        return answer if answer != "" else (default or "")   # like the real prompt: Enter keeps the default
    return ask


class KaCommand(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ka test ")
        self.root = Path(self.temp.name)
        self.env = dict(os.environ)
        source = self.root / "source"
        source.mkdir()
        make_tables(source)
        for f in (source / "data").iterdir():
            f.rename(source / f.name)
        (source / "data").rmdir()
        import pandas as pd
        test = pd.read_csv(source / "test.csv")
        pd.DataFrame({"id": test["id"], "y": 0.5}).to_csv(source / "sample_submission.csv", index=False)
        (self.root / "fake_kaggle.py").write_text(FAKE_CLI)
        (self.root / "info.json").write_text(json.dumps(dict(metric="Area Under Receiver Operating Characteristic Curve",
                                                             deadline="2030-01-01T00:00:00", daily_limit=3)))
        os.environ.update(KAGGLE_AGENT_HOME=str(self.root / "home"), KA_KAGGLE_CLI=json.dumps([sys.executable, str(self.root / "fake_kaggle.py")]),
                          KA_KAGGLE_INFO=str(self.root / "info.json"), KA_FAKE_LOG=str(self.root / "submissions.log"),
                          KA_FAKE_SOURCE=str(source))

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.env)
        self.temp.cleanup()

    def ka(self, argv, answers=()):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = ka.main(argv, ask=scripted(answers))
        return code, out.getvalue() + err.getvalue()

    def submitted(self):
        log = self.root / "submissions.log"
        return [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []

    def test_setup_can_be_answered_again_before_saving(self):
        # First pass: 3 trials, then "n"; second pass keeps defaults with Enter except trials = 2; then save.
        answers = ["claude", "", "", "1", "1024", "0.1", "1", "3", "none", "n",
                   "", "", "", "", "", "", "", "2", "", "y"]
        code, out = self.ka(["setup"], answers)
        self.assertEqual(code, 0, out)
        self.assertEqual(out.count("Your answers:"), 2)
        settings = ka.load_settings()
        self.assertEqual((settings["campaigns"], settings["trials"]), (1, 2))
        from kaggle_agent.supervisor.limits import Limits
        self.assertEqual(Limits(ka.store()).get()["threads"], 1)          # Enter kept the earlier answer

    def test_full_everyday_flow(self):
        code, out = self.ka(["setup"], ["claude", "", "", "1", "1024", "0.1", "1", "3", "none", "y"])
        self.assertEqual(code, 0, out)
        code, out = self.ka(["new", "https://www.kaggle.com/competitions/playground-series-s9e9", "--root", str(self.root)],
                            ["y", "y", "y"])  # detection right, rules read, auto-submit on
        self.assertEqual(code, 0, out)
        self.assertIn("metric: roc_auc", out)
        self.assertIn("target: y", out)
        comp = self.root / "playground-series-s9e9"
        profile = json.loads((comp / ".kaggle-agent/profile.json").read_text())
        self.assertTrue(profile["rules_reviewed"])
        self.assertEqual(profile["metric"], "roc_auc")
        self.assertTrue(profile["deadline"].endswith("+00:00"))
        sub = json.loads((comp / ".kaggle-agent/submission.json").read_text())
        self.assertEqual((sub["slug"], sub["auto"], sub["daily_limit"]), ("playground-series-s9e9", True, 3))
        self.assertTrue((comp / "AGENTS.md").is_file())

        args = argparse.Namespace(dir=str(comp), campaigns=1, trials=2, agent=None,
                                  mock_agent=MockCoder([("baseline logistic", BASELINE), ("hist with interaction feature", IMPROVED)]))
        mock = args.mock_agent
        plain_run = mock.run

        def with_tokens(task, directory, **kwargs):   # like a real agent: reports what it used
            result = plain_run(task, directory, **kwargs)
            result.usage = dict(input_tokens=1200, output_tokens=300, cache_read_input_tokens=50000)
            return result
        mock.run = with_tokens
        out_buffer = io.StringIO()
        with redirect_stdout(out_buffer):
            self.assertEqual(ka.cmd_go(args, scripted([])), 0)
        live = out_buffer.getvalue()
        self.assertIn("trial 1/2", live)
        self.assertIn("Campaign 1/1 done", live)
        self.assertIn("best score", live)
        self.assertIn("tokens: 2k input, 600 output, 100k cached", live)
        self.assertIn("NEW CHAMPION", live)
        self.assertIn("auto-submitted", live)
        sent = self.submitted()
        self.assertEqual(len(sent), 1)                      # one per campaign, newest champion only
        import pandas as pd
        file = pd.read_csv(sent[0]["file"])
        self.assertEqual(list(file.columns), ["id", "y"])
        self.assertEqual(len(file), 300)
        self.assertTrue(file["y"].between(0, 1).all())     # roc_auc -> probabilities

        code, out = self.ka(["status", "--dir", str(comp)])
        self.assertEqual(code, 0, out)
        self.assertIn("Best CV", out)
        self.assertIn("public 0.9", out)                   # refreshed from Kaggle, display only

        code, out = self.ka(["submit", "--dir", str(comp)], ["n"])   # asks first; "n" cancels
        self.assertIn("cancelled", out)
        self.assertEqual(len(self.submitted()), 1)
        code, out = self.ka(["submit", "--dir", str(comp), "--yes"])
        self.assertEqual(code, 0, out)
        self.assertEqual(len(self.submitted()), 2)
        code, out = self.ka(["submit", "--dir", str(comp), "--yes"])
        self.assertEqual(code, 0, out)
        code, out = self.ka(["submit", "--dir", str(comp), "--yes"])  # limit 3 reached
        self.assertEqual(code, 2)
        self.assertIn("Daily submission limit", out)

        code, out = self.ka(["submit", "--limit", "100", "--dir", str(comp)])
        self.assertIn("daily limit 100", out)
        code, out = self.ka(["submit", "--dir", str(comp), "--yes"])    # limit raised: allowed again
        self.assertEqual(code, 0, out)
        code, out = self.ka(["submit", "--auto", "off", "--dir", str(comp)])
        self.assertIn("off", out)
        self.assertFalse(json.loads((comp / ".kaggle-agent/submission.json").read_text())["auto"])

        code, out = self.ka(["dash", "--no-open", "--dir", str(comp)])
        self.assertEqual(code, 0, out)
        page = (comp / ".kaggle-agent/views/dashboard.html").read_text()
        self.assertIn("Best CV", page)
        self.assertIn("hist with interaction feature", page)

        code, out = self.ka(["usage"])
        self.assertEqual(code, 0, out)
        code, out = self.ka(["stop", "--dir", str(comp)])
        self.assertEqual(code, 0, out)
        st = Store(self.root / "home/global.sqlite3")
        self.assertEqual(st.rows("SELECT stop_requested FROM competitions")[0]["stop_requested"], 1)

    def test_git_history_diff_restore(self):
        import shutil
        if not shutil.which("git"):
            self.skipTest("git not installed")
        self.ka(["setup"], ["claude", "", "", "1", "1024", "0.1", "1", "3", "none", "y"])
        code, out = self.ka(["new", "playground-series-s9e9", "--root", str(self.root)], ["y", "y", "n"])
        self.assertIn("Git history: on", out)
        comp = self.root / "playground-series-s9e9"
        self.assertTrue((comp / ".git").is_dir())
        self.assertIn(".kaggle-agent/", (comp / ".gitignore").read_text())
        args = argparse.Namespace(dir=str(comp), campaigns=1, trials=2, agent=None,
                                  mock_agent=MockCoder([("baseline logistic", BASELINE), ("hist with interaction feature", IMPROVED)]))
        with redirect_stdout(io.StringIO()):
            ka.cmd_go(args, scripted([]))
        code, out = self.ka(["history", "--dir", str(comp)])
        self.assertEqual(code, 0, out)
        self.assertIn("NEW CHAMPION", out)
        self.assertIn("champion-001", out)
        self.assertIn("champion-002", out)
        st = Store(self.root / "home/global.sqlite3")
        runs = st.rows("SELECT id,result FROM experiments WHERE fidelity='full' AND result LIKE '%git_commit%' ORDER BY created")
        self.assertEqual(len(runs), 2)
        first = runs[0]["id"]
        code, out = self.ka(["diff", first, "--dir", str(comp)])
        self.assertEqual(code, 0, out)
        self.assertIn("HistGradientBoosting", out)      # champion (hist) vs the first (logistic) run
        code, out = self.ka(["restore", "champion", "--dir", str(comp)])
        self.assertEqual(code, 0, out)
        self.assertIn("HistGradientBoosting", (comp / "restored/champion/train.py").read_text())
        # Data and supervisor state never enter git.
        from kaggle_agent import vcs
        tracked = vcs.git(comp, "ls-files")
        self.assertNotIn("data/", tracked)
        self.assertNotIn(".kaggle-agent", tracked)
        self.assertIn("agent_code/train.py", tracked)

    def test_go_requires_rules_and_setup(self):
        code, out = self.ka(["new", "playground-series-s9e9", "--root", str(self.root)], ["y", "n", "n"])
        self.assertEqual(code, 0, out)
        self.assertIn("rules_reviewed", out)
        code, out = self.ka(["go", "--dir", str(self.root / "playground-series-s9e9")])
        self.assertEqual(code, 2)
        self.assertIn("rules", out)

    def test_agent_model_and_effort(self):
        from unittest.mock import patch
        from kaggle_agent.agents.base import CLIAdapter
        with patch.object(CLIAdapter, "binary", return_value="codex"):
            command = CLIAdapter("codex", model="gpt-x", effort="high").command("p", "out.json", mode="code")
        self.assertIn("--model", command)
        self.assertIn('model_reasoning_effort="high"', command)
        self.assertEqual(command[-1], "-")
        with patch.object(CLIAdapter, "binary", return_value="claude"):
            command = CLIAdapter("claude", model="opus", effort="high").command("p", mode="code")
            plain = CLIAdapter("claude").command("p", mode="code")
        self.assertEqual(command[command.index("--model") + 1], "opus")
        self.assertNotIn("--model", plain)
        with self.assertRaises(ValueError):
            CLIAdapter("codex", effort="turbo")
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as home:
            os.environ["KAGGLE_AGENT_HOME"] = home
            folder = Path(temp) / "comp"
            (folder / ".kaggle-agent").mkdir(parents=True)
            (folder / ".kaggle-agent" / "profile.json").write_text("{}", encoding="utf-8")
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(ka.main(["agent", "codex", "--effort", "high", "--dir", str(folder)]), 0)
                self.assertEqual(ka.main(["agent", "claude", "--model", "opus", "--global"]), 0)
            settings = ka.load_settings()
            self.assertEqual(ka.agent_choice(settings, folder, "codex"), {"effort": "high"})
            self.assertEqual(ka.agent_choice(settings, folder, "claude"), {"model": "opus"})
            self.assertEqual(ka.agent_choice(settings, None, "codex"), {})
            os.environ.pop("KAGGLE_AGENT_HOME")

    def test_outside_competition_folder_is_friendly(self):
        code, out = self.ka(["status", "--dir", str(self.root)])
        self.assertEqual(code, 2)
        self.assertIn("ka new", out)

    def test_label_submission_format(self):
        from kaggle_agent import submit as submissions
        import pandas as pd
        self.ka(["new", "playground-series-s9e9", "--root", str(self.root)], ["n", "id", "y", "classification", "accuracy", "y", "n"])
        comp = self.root / "playground-series-s9e9"
        sample = pd.read_csv(comp / "data/sample_submission.csv")
        sample["y"] = "no"
        sample.to_csv(comp / "data/sample_submission.csv", index=False)
        from tests.test_upgrades import Upgrades
        script = comp / "base.py"
        script.write_text(BASELINE)
        out = comp / "out"
        out.mkdir()
        profile = json.loads((comp / ".kaggle-agent/profile.json").read_text())
        import subprocess
        env = os.environ | dict(KA_DATA_SPEC=json.dumps(profile["data"]), KA_DATA_ROOT=str(comp), KA_TASK="classification",
                                KA_METRIC="accuracy", KA_OUT=str(out), PYTHONPATH=str(Path(__file__).resolve().parents[1]))
        subprocess.run([sys.executable, str(script)], check=True, env=env, cwd=comp)
        from kaggle_agent.__main__ import main as cli
        with redirect_stdout(io.StringIO()):
            cli(["--db", str(self.root / "home/global.sqlite3"), "register-run", "--competition", str(comp),
                 "--oof", str(out / "oof.csv"), "--test", str(out / "test.csv"), "--code", str(script)])
        st = Store(self.root / "home/global.sqlite3")
        competition = st.rows("SELECT id FROM competitions")[0]["id"]
        best = submissions.best_experiment(st, competition, profile)
        path = submissions.build(st, competition, comp, profile, best)
        values = set(pd.read_csv(path)["y"])
        self.assertTrue(values <= {"yes", "no"})            # labels, not probabilities

    def test_metric_names_map(self):
        from kaggle_agent.kaggle_cli import map_metric, slug_from
        self.assertEqual(map_metric("Root Mean Squared Logarithmic Error"), "rmsle")
        self.assertEqual(map_metric("Mean Average Precision @ 3"), "map3")
        self.assertEqual(map_metric("Mean Absolute Percentage Error"), "mape")
        self.assertEqual(slug_from("https://www.kaggle.com/competitions/santa-2025/overview"), "santa-2025")


if __name__ == "__main__":
    unittest.main()
