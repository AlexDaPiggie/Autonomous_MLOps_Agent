Competition URL: $ARGUMENTS (if empty, use the URL in this folder's CLAUDE.md).

Do all of this without waiting for me.

1. Read the Overview, Data, Rules, and Evaluation pages. Write research/brief.md with: goal, metric, data layout, submission format, rules, and any LLM or compute limits.
2. Run EDA to help choose a CV scheme. Look for groups, time order, train/test differences, and leakage. Do not make charts for show.
3. Choose the CV scheme yourself. Write two lines in research/brief.md on why, and what the other option was. Then start a fresh skeptic subagent (kaggle-skeptic.md) to check the choice for leakage. If it finds a problem, fix the scheme.
4. Build a baseline with the chosen folds. Save OOF and test predictions.
5. Follow kaggle-research.md.
6. Follow kaggle-loop.md and keep it running. Create STATE.md and keep it updated.

Only stop for the reasons listed in rules.md. If something is unclear, make the most reasonable choice, write it in STATE.md, and continue.
