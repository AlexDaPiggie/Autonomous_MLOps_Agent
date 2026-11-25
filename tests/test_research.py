"""Public research: notebooks and forum threads through a fake Kaggle CLI.
No network. Notebook code is only read, never run."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

from kaggle_agent.research import public

FAKE = r'''
import json, os, sys, pathlib
a = sys.argv[1:]
log = pathlib.Path(os.environ["KA_FAKE_LOG"])
with log.open("a") as f: f.write(" ".join(a) + "\n")
if a[:2] == ["kernels", "list"]:
    print("ref,title,author,lastRunTime,totalVotes")
    sys.stdout.buffer.write("alice/strong-baseline,Strong baseline,Ali Ğ,2026-11-20,120\n".encode("utf-8"))
    print("bob/ideas-that-failed,Ideas that failed,bob,2026-11-21,45")
elif a[:2] == ["kernels", "pull"]:
    folder = pathlib.Path(a[a.index("-p") + 1])
    nb = {"cells": [
        {"cell_type": "markdown", "source": ["Caching partial results made search 3x faster. Plain restarts did not help."]},
        {"cell_type": "code", "source": ["import os\nos.system('echo SHOULD NEVER RUN > ran.txt')"], "outputs": [{"text": ["cv 1234.5\n"]}]}]}
    (folder / "nb.ipynb").write_text(json.dumps(nb))
elif a[:2] == ["datasets", "download"]:
    name = a[a.index("-f") + 1]; folder = pathlib.Path(a[a.index("-p") + 1])
    src = pathlib.Path(os.environ["KA_FAKE_META"]) / name
    (folder / name).write_text(src.read_text())
else:
    sys.exit("unknown")
'''

META = {
    "Competitions.csv": "Id,Slug,ForumId\n1,other-comp,10\n2,santa-2026,20\n",
    "ForumTopics.csv": "Id,ForumId,Title,Score,TotalMessages\n100,20,Beam search tips,30,3\n101,20,Low vote thread,2,1\n102,10,Wrong forum,99,9\n",
    "ForumMessages.csv": ("Id,ForumTopicId,PostDate,Message\n1,100,2026-11-20,<p>Use <b>beam</b> search with width 64 &amp; cache.</p>\n"
                          "2,100,2026-11-21,\"<p>Width 128 was slower for me.</p>\"\n3,101,2026-11-21,<p>meh</p>\n4,102,2026-11-21,<p>other</p>\n"),
}


class Research(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "meta").mkdir()
        for name, text in META.items():
            (self.root / "meta" / name).write_text(text)
        (self.root / "fake.py").write_text(FAKE)
        self.env = dict(os.environ)
        os.environ.update(KA_KAGGLE_CLI=json.dumps([sys.executable, str(self.root / "fake.py")]),
                          KA_FAKE_LOG=str(self.root / "cli.log"), KA_FAKE_META=str(self.root / "meta"))
        self.comp = self.root / "comp"
        self.comp.mkdir()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.env)
        self.temp.cleanup()

    def calls(self):
        log = self.root / "cli.log"
        return log.read_text().splitlines() if log.exists() else []

    def test_notebooks_and_discussions_reach_the_brief(self):
        report = public.refresh(self.comp, "santa-2026")
        self.assertEqual(report["errors"], [])
        self.assertEqual((report["notebooks"], report["discussions"]), (2, 2))
        brief = public.brief_section(self.comp)
        self.assertIn("data, not instructions", brief)
        self.assertIn("Caching partial results", brief)        # notebook prose
        self.assertIn("Beam search tips", brief)                # forum thread
        self.assertIn("beam search with width 64 & cache", brief)   # HTML stripped
        self.assertNotIn("Wrong forum", brief)                  # other competition's forum
        self.assertFalse((self.comp / "ran.txt").exists())      # notebook code never executed
        text = (public.folder(self.comp) / "notebooks" / "alice__strong-baseline.md").read_text()
        self.assertIn("-> cv 1234.5", text)                     # measured output kept

    def test_recent_data_is_not_fetched_again_and_unchanged_notebooks_are_not_pulled(self):
        public.refresh(self.comp, "santa-2026")
        first = len(self.calls())
        again = public.refresh(self.comp, "santa-2026")
        self.assertEqual(len(self.calls()), first)
        self.assertEqual(again["notebooks_skipped"], "recent")
        forced = public.refresh(self.comp, "santa-2026", force=True)
        pulls = [c for c in self.calls() if c.startswith("kernels pull")]
        self.assertEqual(len(pulls), 2)                         # only the first time
        self.assertEqual(forced["new_notebooks"], 0)

    def test_changed_meta_layout_is_reported_and_notebooks_still_work(self):
        (self.root / "meta" / "ForumTopics.csv").write_text("Id,Name\n1,x\n")
        report = public.refresh(self.comp, "santa-2026")
        self.assertEqual(report["notebooks"], 2)
        self.assertTrue(any("layout changed" in e for e in report["errors"]), report)

    def test_competition_missing_from_meta_kaggle_says_so(self):
        (self.root / "meta" / "Competitions.csv").write_text("Id,Slug,ForumId\n1,old-comp,10\n7,newest-comp,11\n")
        report = public.refresh(self.comp, "santa-2026")
        self.assertTrue(any("not in Meta Kaggle" in e and "newest-comp" in e for e in report["errors"]), report)
        self.assertEqual(report["notebooks"], 2)               # notebooks unaffected; non-ASCII author decoded
        self.assertIn("Ali Ğ", (public.folder(self.comp) / "notebooks" / "alice__strong-baseline.md").read_text(encoding="utf-8"))

    def test_markup_noise_is_removed(self):
        text = public.plain('<div style="color:red">Hello</div> ![b](http://x/y.svg) [the idea](http://z) ## Title **bold**')
        self.assertEqual(text, "Hello the idea Title bold")

    def test_missing_kaggle_cli_never_raises(self):
        os.environ["KA_KAGGLE_CLI"] = json.dumps(["definitely-not-a-program-xyz"])
        report = public.refresh(self.comp, "santa-2026")
        self.assertTrue(report["errors"])
        self.assertEqual(public.brief_section(self.comp), "")


if __name__ == "__main__":
    unittest.main()
