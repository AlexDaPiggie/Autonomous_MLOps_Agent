Run the experiment loop until I say stop or the budget is used.
Start from the latest research/sota_<date>.md and the current best model.

Each round:
1. Pick the top untested idea.
2. Write the stop condition.
3. Make the change, then run the CPU smoke test.
4. Run the full job on Modal (`modal run --detach`).
5. Log the result and update local_leaderboard.md.
6. If it is a new best, follow kaggle-submit.md to decide whether to submit.

Keep an idea only if CV beats the best by more than a small margin AND the per-fold scores agree. Say what margin you chose.
Every 5 experiments, start a fresh subagent with the skeptic prompt (kaggle-skeptic.md) on the last 5 changes. It must read the code, not your summary.
If 8 experiments in a row do not beat the best, run the stuck protocol (kaggle-stuck.md).
Keep each report short. Do not paste long logs.
