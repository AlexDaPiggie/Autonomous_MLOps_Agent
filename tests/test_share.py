"""`ka export` / `ka import`: history must survive a move to another folder and PC."""
import io
import json
import os
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import shutil
import time
import unittest
import zipfile

from kaggle_agent import share
from kaggle_agent.__main__ import competition_id
from kaggle_agent.agents.base import MockCoder
from kaggle_agent import ka
from kaggle_agent.execution.gates import GateError
from tests import test_ka   # as a module, so its tests are not collected twice
from tests.test_ka import scripted
from tests.test_upgrades import BASELINE, IMPROVED


class Relocate(unittest.TestCase):
    def test_every_stored_spelling_moves_and_siblings_do_not(self):
        old, new = r"C:\Users\a\Coding\comp", r"D:\work\my comp"
        for sep in ("\\", "\\\\", "\\\\\\\\", "/"):
            text = sep.join(["C:", "Users", "a", "Coding", "comp", "data"])
            self.assertEqual(share.relocate(text, old, new), sep.join(["D:", "work", "my comp", "data"]))
        self.assertEqual(share.relocate(r"c:\users\A\coding\COMP", old, new), new)
        for sibling in (old + "-2", old + "_old", old + ".bak"):
            self.assertEqual(share.relocate(sibling, old, new), sibling)


class Share(unittest.TestCase):
    setUp, tearDown, ka = test_ka.KaCommand.setUp, test_ka.KaCommand.tearDown, test_ka.KaCommand.ka

    def build(self):
        self.ka(["setup"], ["claude", "", "", "1", "1024", "0.1", "1", "3", "none", "y"])
        code, out = self.ka(["new", "https://www.kaggle.com/competitions/playground-series-s9e9", "--root", str(self.root)],
                            ["y", "y", "y"])
        self.assertEqual(code, 0, out)
        comp = self.root / "playground-series-s9e9"
        self.go(comp, "baseline logistic", BASELINE)
        return comp

    def go(self, comp, name, script):
        import argparse
        args = argparse.Namespace(dir=str(comp), campaigns=1, trials=1, agent=None, mock_agent=MockCoder([(name, script)]))
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(ka.cmd_go(args, scripted([])), 0, out.getvalue())

    def history(self, comp):
        st = ka.store()
        cid = competition_id(comp)
        return (st.rows("SELECT champion FROM competitions WHERE id=?", (cid,))[0]["champion"],
                len(st.rows("SELECT id FROM experiments WHERE competition=?", (cid,))))

    def test_export_import_into_another_folder_then_resume(self):
        comp = self.build()
        champion, runs = self.history(comp)
        (comp / ".env").write_text("SECRET=1")
        (comp / ".kaggle-agent" / "workspace" / "scratch").mkdir(parents=True, exist_ok=True)
        (comp / ".kaggle-agent" / "workspace" / "scratch" / "big.bin").write_bytes(b"x")
        code, out = self.ka(["export", "--dir", str(comp)])
        self.assertEqual(code, 0, out)
        archive = comp.parent / f"{comp.name}-share.zip"
        names = zipfile.ZipFile(archive).namelist()
        self.assertFalse([n for n in names if n.endswith(".env") or "workspace/" in n or "settings.json" in n])

        # A different PC: its own empty history and a folder with another name.
        os.environ["KAGGLE_AGENT_HOME"] = str(self.root / "other home")
        self.ka(["setup"], ["claude", "", "", "1", "1024", "0.1", "1", "3", "none", "y"])
        shutil.move(comp, self.root / "gone")   # nothing may still point at the old place
        moved = self.root / "elsewhere" / "renamed comp"
        code, out = self.ka(["import", str(archive), "--to", str(moved)])
        self.assertEqual(code, 0, out)
        self.assertEqual(self.history(moved), (champion, runs))
        self.assertFalse(json.loads((moved / ".kaggle-agent" / "submission.json").read_text())["auto"])
        st = ka.store()
        for row in st.rows("SELECT path FROM predictions"):
            self.assertTrue(Path(row["path"]).is_file(), row["path"])
            self.assertTrue(Path(row["path"]).is_relative_to(moved.resolve()))

        self.go(moved, "hist with interaction feature", IMPROVED)   # the loop continues
        new_champion, new_runs = self.history(moved)
        self.assertGreater(new_runs, runs)   # a trial records screen and full runs
        self.assertNotEqual(new_champion, champion)

        code, out = self.ka(["import", str(archive), "--to", str(moved)])
        self.assertNotEqual(code, 0)   # never overwrites

    def test_interrupted_run_exports_and_the_copy_resumes(self):
        comp = self.build()
        st = ka.store()
        key = st.rows("SELECT key FROM remote_jobs LIMIT 1")[0]["key"]
        (comp / ".kaggle-agent" / "jobs" / key / "result.json").unlink(missing_ok=True)
        with st.transaction() as db:   # as left behind by a killed `ka go`
            db.execute("UPDATE remote_jobs SET state='INTENT', pid=999999, process_created=1.0 WHERE key=?", (key,))
            db.execute("UPDATE experiments SET state='RUNNING' WHERE id=?", (key,))
        (comp / ".kaggle-agent" / "jobs" / key / "status.json").write_text('{"state":"RUNNING","pid":999999,"process_created":1.0}')
        result = share.export(st, comp)
        self.assertEqual(result["interrupted"], [key[:8]])
        self.assertEqual(st.rows("SELECT state FROM remote_jobs WHERE key=?", (key,))[0]["state"], "INTENT")   # untouched
        os.environ["KAGGLE_AGENT_HOME"] = str(self.root / "other home")
        self.ka(["setup"], ["claude", "", "", "1", "1024", "0.1", "1", "3", "none", "y"])
        moved = share.import_(ka.store(), result["zip"], self.root / "resumed")["folder"]
        before = self.history(moved)[1]
        self.go(moved, "hist with interaction feature", IMPROVED)
        self.assertGreater(self.history(moved)[1], before)

    def test_export_refuses_while_running_and_import_refuses_unsafe_zip(self):
        comp = self.build()
        st = ka.store()
        with st.transaction() as db:
            db.execute("UPDATE competitions SET lease_until=?", (time.time() + 60,))
        with self.assertRaises(GateError):
            share.export(st, comp)
        with st.transaction() as db:
            db.execute("UPDATE competitions SET lease_until=NULL")
        archive = share.export(st, comp)["zip"]
        bad = self.root / "bad.zip"
        with zipfile.ZipFile(archive) as source, zipfile.ZipFile(bad, "w") as out:
            for info in source.infolist():
                out.writestr(info, source.read(info))
            out.writestr("folder/../../escape.txt", "x")
        with self.assertRaises(GateError):
            share.import_(st, bad, self.root / "x" / "target")
        self.assertFalse((self.root / "escape.txt").exists())
        self.assertFalse((self.root / "x" / "target").exists())


if __name__ == "__main__":
    unittest.main()
