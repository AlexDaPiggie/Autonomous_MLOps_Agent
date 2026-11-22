Run bounded campaigns within rules.md budgets. Read compact STATE.md, current champions and the relevant research synthesis.
1. Choose a hypothesis about our own pipeline and freeze the baseline (public outputs or public tools re-run on them are not a hypothesis; see "Own pipeline first" in rules.md). Reuse a configurable runner; default to 2-4 config variants. Usually change one thing; label coherent reframes and ablate successful packages.
2. Declare paired-gain margin, trials, cost/runtime bounds and stop conditions. Reserve cost for every scheduled job before launch.
3. Smoke-test changed code on the real local train/inference path. Apply kaggle-skeptic.md to new feature/validation logic or imported code on the main session.
4. Launch a detached scripted Modal batch. Python trains, scores, saves OOF/test artifacts plus registry metadata, logs results and checkpoints without an LLM call per iteration.
5. Review one compact batch summary. Inspect detailed logs only for failures. Reconcile spend and update STATE.md and local_leaderboard.md.
6. Separately evaluate standalone improvement and contribution to the frozen ensemble. Refit baseline and candidate combiners on identical permitted rows; compare held-out paired fold deltas using rules.md. Retain valid complementary models even if their standalone score is weaker. Log inference cost.
7. Follow kaggle-submit.md for a worthy candidate. Preserve failed predictions as evidence.
After each campaign, consider refinement, a different family or a new representation; do not target a model count. Eight consecutive experiments of our own pipeline without validated standalone OR ensemble progress trigger kaggle-stuck.md; public merges do not reset the counter.
No mandatory review subagent every five runs. Reuse reviews of unchanged code; review material changes and final candidates. Stop/checkpoint under rules.md limits.
Never pause to ask whether to continue: follow the NEVER STOP rule in rules.md (Session memory).
