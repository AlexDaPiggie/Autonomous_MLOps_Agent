Read the prediction registry and relevant leaderboard entries.
1. Validate source provenance, row IDs/order, data/fold hashes, class/candidate order, scale and stopping/tuning policy. Exclude invalid artifacts. Regenerate incompatible external predictions on agreed folds when affordable.
2. Predeclare a broad quality floor and evaluation budget. Do not filter solely to top standalone CV; retain genuinely complementary candidates. Correlation is diagnostic, not proof of benefit.
3. Start with a simple blend and a regularized metric-appropriate combiner: clipped-logit logistic regression for class probabilities, a suitable linear/ridge model for regression, candidate-aligned rank/score combinations for ranking evaluated with the actual metric.
4. Fit/tune combiners only on allowed training partitions. Compare candidate and baseline using the same held-out procedure and refit both on identical permitted rows. Report standalone CV, paired ensemble deltas and added inference cost.
5. Label base OOF, conditional meta-CV, replay/training and fully nested scores separately. Conditional meta-CV over an existing OOF library is not independent full-pipeline validation. Use inner stopping/tuning splits for strict outer evaluation.
6. Cache predictions; do not retrain bases merely to reblend. Fold averaging and full refits are both allowed if validated and documented.
7. Try hill climbing or a nonlinear stack only for a concrete opportunity within budget; deeper predictive stacks need appropriate nesting. No mandatory NN/GBDT stacker.
8. Prepare the best validated candidate and a safer diverse final candidate when competition rules allow, then follow kaggle-submit.md.
Never select models/weights by public score or test predictions.
