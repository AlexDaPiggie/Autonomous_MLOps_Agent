Stuck protocol. Do these steps in order and write research/stuck_<date>.md.

1. Validity audit. Does local CV still track the leaderboard? Any leaks, or rows dropped from OOF? List what you checked and how.
2. Error analysis. Where is the model worst (rows, groups, classes, time ranges)? What would fix the worst 10 percent?
3. Re-read. Open 5 top write-ups from similar past competitions. List what they do that we do NOT do.
4. Reframe. Write 3 different ways to frame this problem (different target, representation, or split of the task). Pick the cheapest test for each.
5. Diversity. Build ONE model from scratch with a different model family and different features. Do not tweak an existing one.
6. Targeted refinement. Run an ablation to find the pipeline part that matters most. Spend the next 5 experiments only on it.
7. Budget check. How much budget is left? Is more work likely to help?
8. Write STUCK_REPORT.md with what you found. Then keep going: run the best reframe or diversity idea. Do NOT declare the ceiling reached yourself. Do not wait for me.
