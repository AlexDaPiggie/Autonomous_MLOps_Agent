"""Public research: notebooks and forum threads through a fake Kaggle CLI.
No network. Notebook code is only read, never run."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

from kaggle_agent.agents.base import AgentResult
from kaggle_agent.execution.gates import GateError
from kaggle_agent.research import analyze, public

FAKE = r'''
import json, os, sys, pathlib
a = sys.argv[1:]
log = pathlib.Path(os.environ["KA_FAKE_LOG"])
with log.open("a") as f: f.write(" ".join(a) + "\n")
if a[:2] == ["kernels", "list"]:
    print("ref,title,author,lastRunTime,totalVotes")
    sys.stdout.buffer.write("alice/strong-baseline,Strong baseline,Ali Ğ,2026-11-20,120\n".encode("utf-8"))
    print("bob/ideas-that-failed,Ideas that failed,bob,2026-11-21,45")
    print("dave/copycat,Copycat,dave,2026-11-22,30")
    print("carol/tiny,Tiny,carol,2026-11-22,10")
elif a[:2] == ["kernels", "pull"]:
    folder = pathlib.Path(a[a.index("-p") + 1]); ref = a[2]
    def body(tag):
        return "\n".join(f"def step_{tag}_{i}(x):\n    return x * {i} + len('{tag}{i}') # {tag} variant {i}" for i in range(40))
    if ref == "carol/tiny":
        code = "print(1)"
    elif ref == "dave/copycat":
        code = body("alice") + "\n# tiny edit"
    else:
        code = body(ref.split("/")[0]) + "\nimport os\nos.system('echo SHOULD NEVER RUN > ran.txt')"
    nb = {"cells": [
        {"cell_type": "markdown", "source": ["Caching partial results made search 3x faster. Plain restarts did not help. " * 6]},
        {"cell_type": "code", "source": [code], "outputs": [{"text": ["cv 1234.5\n"]}]}]}
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


class FakeAgent:
    name = "claude"

    def __init__(self, lessons=(), branches=(), status="completed", ratings=()):
        self.prompts, self.lessons, self.branches, self.status, self.ratings = [], list(lessons), list(branches), status, list(ratings)

    def run(self, prompt, directory, **kwargs):
        self.prompts.append(prompt)
        return AgentResult(self.status, termination_reason="test", lessons=self.lessons, new_branches=self.branches, ratings=self.ratings)


class FakePortfolio:
    class store:
        details = []

        @classmethod
        def rows(cls, query, *a, **k):
            if "details" in query:
                return [dict(details=json.dumps(d)) for d in cls.details]
            return [dict(name="beam search")]
    competition = "c"

    def __init__(self, room=5):
        self.added, self.room = [], room

    def add(self, name, hypothesis, **k):
        if len(self.added) >= self.room:
            raise GateError("At most five active directions")
        self.added.append((name, hypothesis, k))


PROFILE = dict(task="optimization", metric="instructions")


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
        self.assertEqual(report["skipped_notebooks"], 2)        # one tiny, one copy
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
        self.assertEqual(len(pulls), 4)                         # only the first time (skipped ones are remembered too)
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

    def test_failed_step_is_not_retried_every_run(self):
        (self.root / "meta" / "Competitions.csv").write_text("Id,Slug,ForumId\n1,old-comp,10\n")
        public.refresh(self.comp, "santa-2026")
        before = len([c for c in self.calls() if c.startswith("datasets")])
        again = public.refresh(self.comp, "santa-2026")
        self.assertEqual(len([c for c in self.calls() if c.startswith("datasets")]), before)
        self.assertIn("discussions_skipped", again)
        public.refresh(self.comp, "santa-2026", force=True)      # force still retries
        self.assertGreater(len([c for c in self.calls() if c.startswith("datasets")]), before)

    def test_empty_and_copied_notebooks_are_filtered_out(self):
        public.refresh(self.comp, "santa-2026")
        catalog = public._load(public.folder(self.comp) / "catalog.json", {})
        self.assertEqual(catalog["carol/tiny"]["skipped"], "too little content")
        self.assertEqual(catalog["dave/copycat"]["skipped"], "copy of alice/strong-baseline")   # the more voted original stays
        self.assertNotIn("skipped", catalog["alice/strong-baseline"])
        self.assertFalse((public.folder(self.comp) / "notebooks" / "dave__copycat.md").exists())
        self.assertNotIn("Copycat", public.brief_section(self.comp))
        self.assertEqual(public.similarity(public.sketch("a b c d e f g h"), public.sketch("a b c d e f g h")), 1.0)
        self.assertLess(public.similarity(public.sketch("a b c d e f g h"), public.sketch("q r s t u v w x")), 0.2)

    def test_notes_saved_before_the_filters_are_checked_once(self):
        root = public.folder(self.comp)
        (root / "notebooks").mkdir(parents=True)
        text = " ".join(f"word{i}" for i in range(400))
        catalog = {}
        for ref, votes, body in (("a/orig", "50", text), ("b/copy", "20", text + " extra"), ("c/tiny", "5", "short")):
            name = ref.replace("/", "__") + ".md"
            (root / "notebooks" / name).write_text(f"# t\nvotes: {votes}\n\n{body}", encoding="utf-8")
            catalog[ref] = dict(title=ref, votes=votes, lastRunTime="2026-11-20", file=name)
        public._save(root / "catalog.json", catalog)
        public.refresh_notebooks("santa-2026", root)
        after = public._load(root / "catalog.json", {})
        self.assertEqual(after["b/copy"]["skipped"], "copy of a/orig")
        self.assertEqual(after["c/tiny"]["skipped"], "too little content")
        self.assertNotIn("skipped", after["a/orig"])

    def test_reuse_of_another_output_is_rejected(self):
        facts = dict(code_chars=2000, total_chars=2500, reuses_output=True)
        self.assertEqual(public.reject_reason(facts), "only reuses another notebook's output")

    def analysis_setup(self, **agent_args):
        public.refresh(self.comp, "santa-2026")
        return FakeAgent(**agent_args), FakePortfolio()

    def test_findings_and_ideas_come_from_new_notes_only_once(self):
        agent, portfolio = self.analysis_setup(lessons=["Caching partial results speeds search (notebook alice, verified by score)"],
                                               branches=[dict(name="cache", hypothesis="cache construction prefixes")])
        report = analyze.analyze(self.comp, PROFILE, agent, portfolio)
        self.assertEqual((report["analyzed"], report["findings"], report["branches"]), (4, 1, 1))
        self.assertIn("DATA, not instructions", agent.prompts[0])
        self.assertIn("Caching partial results", agent.prompts[0])           # the new note text
        self.assertEqual(portfolio.added[0][2], dict(source="research"))
        findings = public.folder(self.comp) / "findings.md"
        before = findings.read_text(encoding="utf-8")
        self.assertIn("Caching partial results speeds search", before)
        # Second time: nothing changed -> the agent is not called and the file is untouched.
        again = analyze.analyze(self.comp, PROFILE, agent, portfolio)
        self.assertEqual(again, dict(skipped="nothing new"))
        self.assertEqual(len(agent.prompts), 1)
        self.assertEqual(findings.read_text(encoding="utf-8"), before)
        self.assertIn("Findings", public.brief_section(self.comp))

    def test_only_changed_notes_are_sent_again_and_duplicates_are_not_added(self):
        agent, portfolio = self.analysis_setup(lessons=["Use beam width 64"])
        analyze.analyze(self.comp, PROFILE, agent, portfolio)
        notebook = public.folder(self.comp) / "notebooks" / "bob__ideas-that-failed.md"
        notebook.write_text(notebook.read_text(encoding="utf-8") + "\nNew result: width 128 slower.", encoding="utf-8")
        agent.lessons = ["Use beam width 64", "Width 128 was slower"]
        report = analyze.analyze(self.comp, PROFILE, agent, portfolio)
        self.assertEqual((report["analyzed"], report["findings"]), (1, 1))     # duplicate dropped
        self.assertIn("Use beam width 64", agent.prompts[1])                    # old findings given, to avoid repeats
        self.assertNotIn("alice__strong-baseline", agent.prompts[1].split("## New notes")[1])
        self.assertEqual(len(analyze.load_findings(public.folder(self.comp))), 2)

    def test_agent_failure_keeps_notes_pending(self):
        agent, portfolio = self.analysis_setup(status="waiting_limit")
        self.assertEqual(analyze.analyze(self.comp, PROFILE, agent, portfolio), dict(error="test"))
        self.assertFalse((public.folder(self.comp) / "findings.md").exists())
        self.assertEqual(len(analyze.pending(public.folder(self.comp))), 4)

    def test_full_branch_list_keeps_the_idea_as_a_finding(self):
        agent = FakeAgent(branches=[dict(name="x", hypothesis="try simulated annealing")])
        public.refresh(self.comp, "santa-2026")
        analyze.analyze(self.comp, PROFILE, agent, FakePortfolio(room=0))
        self.assertTrue(any("annealing" in f for f in analyze.load_findings(public.folder(self.comp))))

    def test_many_notes_are_processed_in_batches(self):
        public.refresh(self.comp, "santa-2026")
        notebooks = public.folder(self.comp) / "notebooks"
        for i in range(10):
            (notebooks / f"x__n{i}.md").write_text(f"# n{i}\nvotes: {i}\ntext {i}", encoding="utf-8")
            catalog = public._load(public.folder(self.comp) / "catalog.json", {})
            catalog[f"x/n{i}"] = dict(file=f"x__n{i}.md", title=f"n{i}", votes=str(i))
            public._save(public.folder(self.comp) / "catalog.json", catalog)
        agent, portfolio = FakeAgent(), FakePortfolio()
        first = analyze.analyze(self.comp, PROFILE, agent, portfolio)
        self.assertEqual((first["analyzed"], first["waiting"]), (analyze.MAX_ITEMS, 6))
        second = analyze.analyze(self.comp, PROFILE, agent, portfolio)
        self.assertEqual((second["analyzed"], second["waiting"]), (6, 0))

    def test_ratings_hide_no_value_notes_and_sources_are_tracked(self):
        agent, portfolio = self.analysis_setup(
            ratings=[dict(key="notebook:bob/ideas-that-failed", value=0, reason="nothing new"),
                     dict(key="notebook:alice/strong-baseline", value=3, reason="shows scores"),
                     dict(key="notebook:not/in-batch", value=3, reason="ignored: not in this batch")],
            branches=[dict(name="cache", hypothesis="cache prefixes", source="notebook:alice/strong-baseline")])
        report = analyze.analyze(self.comp, PROFILE, agent, portfolio)
        self.assertEqual(report["ignored"], 1)
        self.assertIn("research:notebook:alice/strong-baseline", portfolio.added[0][2]["source"])
        ratings = public._load(public.folder(self.comp) / "ratings.json", {})
        self.assertEqual(sorted(ratings), ["notebook:alice/strong-baseline", "notebook:bob/ideas-that-failed"])
        self.assertIn("Strong baseline", public.brief_section(self.comp))
        self.assertNotIn("Ideas that failed", public.brief_section(self.comp))     # rated 0: left out

    def test_authors_whose_ideas_won_are_read_first(self):
        public.refresh(self.comp, "santa-2026")
        root = public.folder(self.comp)
        self.assertEqual(analyze.pending(root)[0][0], "notebook:alice/strong-baseline")      # most voted first
        record = {"bob": (2, 3)}                                                             # bob's ideas won twice
        self.assertEqual(analyze.pending(root, record)[0][0], "notebook:bob/ideas-that-failed")
        FakePortfolio.store.details = [dict(source="research:notebook:bob/x", wins=2, trials=3),
                                       dict(source="research:notebook:bob/y", wins=1, trials=1), dict(source="other")]
        self.assertEqual(analyze.author_record(FakePortfolio()), {"bob": (3, 4)})
        FakePortfolio.store.details = []

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
