Check whether the current best result may be submitted under the Submission rules in rules.md.

1. Compare its CV with the last submission's CV, fold by fold, using the margin test in rules.md (wins most folds, or mean gain beats the spread of per-fold differences). Skip this check for the first submission or a final-pick candidate.
2. Run the skeptic review (kaggle-skeptic.md) on the code behind it. Only real problems block (see rules.md).
3. Check the submission file: row count, columns, no NaN, IDs match the sample file.
4. Count today's submissions.

If every check passes, submit. Then log it in SUBMISSIONS.md.
If any check fails, do not submit. Write one short paragraph saying which check failed and why.
Either way, finish with a short report: CV, per-fold scores, the CV vs public score gap so far, and any risk of overfitting to the public leaderboard.
