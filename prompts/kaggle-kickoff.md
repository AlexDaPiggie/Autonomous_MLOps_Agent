Competition URL: $ARGUMENTS; otherwise use AGENTS.md (or CLAUDE.md). If no URL there, ask.
Proceed without routine confirmation.
1. Read Overview, Data, Rules and Evaluation. Write research/brief.md: goal, metric, layout, submission format, external-data/LLM/compute rules and deadline.
2. Run targeted EDA for groups, time, train/test differences and leakage. Investigate original-data provenance where relevant.
3. Choose and persist folds; explain the choice. Apply kaggle-skeptic.md on the main session and fix real validity problems.
4. Create CONFIG.md: metric direction, folds, paired-gain margin, inference constraints and Modal budgets from rules.md. Existing explicit settings take precedence.
5. Build a reusable baseline runner, smoke-test the real path locally, then save OOF/test plus registry metadata on a completed full run.
6. Follow kaggle-research.md, then kaggle-loop.md. Create compact STATE.md.
Stop under rules.md limits. Document routine assumptions; ask only for essential missing input.

For the optional executable supervisor, use OPERATING_GUIDE.md to create a reviewed
typed profile and frozen dataset/splits. Legacy CONFIG/STATE limits and active jobs
must be reconciled before setting legacy_limits_reviewed. Initialization alone does
not authorize remote execution or submissions.
