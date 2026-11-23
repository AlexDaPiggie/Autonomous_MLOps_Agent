Find supported approaches and write research/sota_<date>.md. Do not implement during this research pass.
1. Read STATE.md, relevant new experiment results and the previous synthesis. Identify what changed, the unanswered question and the next decision.
2. Reuse existing source notes. Reopen or find sources only when their version changed, their evidence is uncertain, or a named question could change the next decision. Prefer executed end-to-end solutions and findings write-ups with measured results (what worked, what failed, ablations) over high scores without explanation; broaden only for specific gaps.
2b. Find sources by CATEGORY, not by title or keyword (set by user 2026-11-23). For notebooks: `kaggle kernels list --competition <slug> --sort-by X --page-size 30` for X in commentCount (findings and debates), hotness (new strong work), voteCount (proven classics), dateRun (updates of notebooks we already noted); scoreAscending only to locate the best programs. Union the lists, then rank the pool by CONTENT (pull the source text: measured tables, "did not work"/ablation sections, real search code vs merge-only code), never by title. For discussions use the forum's own sorts (Hot, Most votes, Most comments, Recent) in the browser. Also check: notebooks of a watchlist of proven originators, sources cited in credits sections, and dataset descriptions / linked repos of strong notebooks. For notebooks already noted, compare the new text with the saved copy and re-read only what changed. Keep research/catalog.tsv (ref, author, last run seen, type original/merge/eda, note file, last checked).
3. For newly reviewed or materially changed sources, read relevant documentation, code, outputs and result-bearing figures. Record source, method, evidence, limitations, reusable code and prior attempts in research/notebook_notes/<name>.md. Update SYNTHESIS.md with material changes and links; do not duplicate unchanged notes.
3a. Reading protocol (set by user 2026-11-23). Budget by size, not time: a deep read is about 5-10k tokens per notebook.
- Triage first: top of the markdown, results tables, "what did not work" and the changelog. Decide: skip, one-line note, or deep read.
- Deep read: the markdown in full. Code only by targeted search for the key parts (main search / model, settings, constants), at most ~20k characters per notebook. Never read packed or base64 program data, embedded submissions or credits lists.
- Extract every number with its baseline and setup (data split, compute, time). Mark each claim measured or only stated.
- Check claims: does the code do what the text says; is there a control; was the gain measured on their own work or after a merge.
- Hidden value: version history / changelog, comments under the notebook, attached datasets and linked repos (descriptions first; scan code before any reuse).
- Map to us: already in our pipeline / tested (Exx) / cheapest test here. This goes under "Tested by us".
- Read code in full only when we plan to reuse it, as a file scan, not as reading.
3b. Note template (research/notebook_notes/<name>.md; one file per source, or one per reading round for short entries). Discussions use the same template with `Type: discussion` and the thread URL.
```
# <owner/slug or thread title> (<date read>, version / last run seen)
Type: original | merge | eda | discussion   Score: <if any>   Link: <url>
## Method (plain words)
## Evidence (numbers, controls, what failed)
## Limits / doubts
## Reusable (code, license, data)
## Tested by us
- <Exx> <date>: <what we ran> -> <result> (<keep/drop>)   or "not tested yet: <cheapest test>"
```
When an experiment tests an idea from a source, add a line under "Tested by us" in that note and put the note file name in the experiments.tsv note column. When a note is written or updated, set its row in research/catalog.tsv to status `noted` with the note file name.
4. Search local previous solutions for adapters. Where relevant, investigate original-data provenance/generating process and external-data permissions. Treat uncertain generator claims as hypotheses.
5. Search papers/docs for specific unresolved methods. Filter by inspectable primary evidence and validation quality, not AI authorship or popularity. Record why retained/dropped.
6. Output idea | source | evidence/limitations | expected benefit (unknown unless supported) | estimated compute cost | leakage risk | cheapest useful test. Distinguish literature observations, hypotheses and locally demonstrated results.
7. Rank by likely information/gain per dollar. Include a representation/reframe when justified; no mandatory count. Skip disproven ideas unless the setup changes materially. Set a research time or source budget before starting; stop when the best affordable test is specified, further sources are unlikely to change the decision, or the budget is reached. Report fewer than five ideas when evidence is sparse.
Read on the main agent session. No automatic reading swarm or default LLM-predictor training. Use optional second opinions only under rules.md.