Read local_leaderboard.md and all OOF files. Drop models below a CV threshold you propose, and any model the skeptic flagged.
Build: (a) logistic regression on the logits of all kept models, (b) hill climbing, (c) one NN or GBDT stacker with nested folds.
Report CV for each. Do not use the test set to choose. Prepare submission.csv for the best two, then follow kaggle-submit.md to decide whether to submit.
