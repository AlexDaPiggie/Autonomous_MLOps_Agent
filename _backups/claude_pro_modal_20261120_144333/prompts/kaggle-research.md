Task: find the best known approaches for this competition. Write research/sota_<date>.md. Do not implement anything yet.

1. Find the 3 most similar PAST Kaggle competitions (same data type and metric). Read the top 10 write-ups of each.
2. Read the top public notebooks of THIS competition by leaderboard score and by votes, especially end-to-end ones that actually solved the task. Read their documentation, code, outputs and figures (extract the PNGs and look at them). Write notes in research/notebook_notes/<name>.md and a SYNTHESIS.md (see "Learn from public notebooks" in rules.md). Pure blends: only note where their programs or predictions came from.
3. Search for papers and blog posts from the last 12 months on this problem type. Run a SEPARATE search for each idea.
4. Source filter. Keep a source only if it gives a result I can check (numbers, code, or a leaderboard rank). Prefer authors with real Kaggle results and posts with detailed, positive comments. Skip anything that looks AI-written, generic, or has no evidence. For each source, note why you kept or dropped it.
5. Output a table: idea | source link | evidence | expected gain | GPU cost | leakage risk | how to test in under 1 hour.
6. Rank by gain per cost. Mark each idea "tweak" or "reframe". Include at least 3 reframes (a different target, a different data representation, a different way to split the task).
7. Skip ideas we already tried. Check the experiment log first.
