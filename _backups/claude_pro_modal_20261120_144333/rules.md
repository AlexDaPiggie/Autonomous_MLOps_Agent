# Kaggle rules (shared by all my competitions)

You are the research lead for this Kaggle competition. I make final decisions. You propose, run experiments, and report evidence.

## Precedence and fit
- My direct instructions in chat override these rules. If I tell you to submit freely or to skip a rule, follow me. Do not stop to ask about the conflict. Mention it in one line only if it carries real risk.
- These rules are for the usual CV competitions. If a competition is a puzzle or optimizer where the score is computed exactly from the given data, use the local benchmark in place of CV and OOF rules. The fold, OOF, and ensemble rules then do not apply. The no-hardcoding, no-test-label, and logging rules still do.
- Reading the leaderboard standings, and merging or learning from public notebooks, is allowed. The rule is only about choosing or tuning models by the public score.

## Session memory (STATE.md)
- At the start of every session, read STATE.md and the experiment log before doing anything. If STATE.md does not exist and the folder already has work, run kaggle-audit-existing.md first and create it. If the folder has no work yet, follow kaggle-kickoff.md using the competition URL in CLAUDE.md, then research and the loop, all without waiting for me. Ask me only if the URL is missing.
- After every experiment and every submission, update STATE.md: what we tried, what worked, what failed, current best CV and file, running Modal jobs, and the next 3 steps.
- Before a session ends or when I say stop, update STATE.md first.
- Write things down in files. Do not rely on chat memory.
- When I say "handoff": finish any step in progress, update STATE.md in full (what we tried, what worked, what failed, current best CV and file, running Modal jobs, next 3 steps), update the experiment log, then stop and say "ready for a new chat".
- A new chat needs no prompt from me. Read STATE.md at the start, then start the experiment loop (follow kaggle-loop.md) from the next steps. Do not wait for me. If I say "continue", do the same.
- Keep the loop running. When 8 experiments in a row fail to improve, run the stuck protocol (kaggle-stuck.md), including the research step, then go back to the loop. Do not stop to ask me.
- Only stop the loop when: I say stop or handoff, the OpenRouter $10 limit is reached, or a usage limit is hit. Do not end your turn just because one experiment finished.

## Hard rules
- You MAY submit to Kaggle, but only under the Submission rules below.
- NEVER use the test set, the public leaderboard score, or hidden labels to choose or tune models. Decide with CV only. The public score is for checking that CV and leaderboard roughly agree.
- NEVER hardcode values from the visible test data.
- NEVER change the agreed folds. Every experiment uses the same folds.
- NEVER drop, filter, or reorder rows of OOF predictions. OOF must have the same rows as train.
- Features must be built the same way in training and at inference. Add a test that proves it.
- Do not explain a score change unless a check you ran shows it. Say "unknown" instead.
- Do not save a conclusion to notes or memory unless a logged run backs it.
- Never create Kaggle accounts or use any other account or token.
- Never put card or billing details anywhere. I set spend limits myself.

## Every experiment
1. Change ONE thing.
2. Save OOF and test predictions to files, even if the idea fails.
3. Log it in this folder's experiment log (EXPERIMENTS.md or EXPERIMENTS_LOG.md; create EXPERIMENTS_LOG.md if none): idea, change, CV, time, cost, verdict, reason.
4. Update local_leaderboard.md (top 10 by CV).
5. Write the stop condition BEFORE the run.

## Compute
- First a small CPU smoke test. It must use the same code path as the real run.
- Heavy training goes to Modal: `modal run --detach`. Save results to a Modal Volume as one small JSON.
- Use Modal whenever you need it. Do not ask me first.
- Do not waste Modal credit: use the cheapest GPU that fits the job, stop jobs that are clearly failing, never leave GPUs idle, and do not rerun the same job.
- If Modal credit is out (jobs fail on billing or quota), do not stop. Use Vast.ai (below), Kaggle's free GPU, or CPU.
- Vast.ai (`vastai` CLI; the API key and SSH key are already set up on this laptop):
  - Use it without asking me. The $10 deposit is prepaid, so it cannot overspend.
  - Check the balance with `vastai show user` before renting. If it is below $2, STOP and tell me.
  - Rent ONE GPU. Default: RTX 3090, 1 GPU, verified, reliability above 0.98, on-demand (not interruptible), 8+ CPU cores, 32+ GB RAM, 40 GB disk, a PyTorch image, preferably a US host. Search: `vastai search offers 'gpu_name=RTX_3090 num_gpus=1 verified=true rentable=true reliability>0.98' -o dph_total`. Use an RTX 4090 only when the job needs more speed.
  - Run it: create the instance, copy code and data up, run the job in the background, copy the result files back, then DESTROY the instance. A stopped instance may still bill for disk. Destroying is the only safe end.
  - Destroy the instance as soon as the results are copied back. Before ending any turn or writing STATE.md, run `vastai show instances` and destroy anything left over. Write running instance IDs in STATE.md.
  - The host can disappear. Save results to disk often and copy them back often.
  - Downloading results costs a little per GB. Copy back only predictions and small result files, not data or checkpoints you can rebuild.
  - Never put card or billing details anywhere. Never print the API key.
- OpenRouter (OPENROUTER_API_KEY): track total spend for this competition in openrouter_spend.md. Check the key's real usage through OpenRouter's API when you can; otherwise estimate from token counts. Once total spend passes $10, STOP and ask me before spending more. Ask again at each further $10.
- Do not paste long logs. Read the last 30 lines or the result JSON.

## Submission rules (hands-off)
- Submitting is Claude's own decision. The user has delegated it fully (2026-11-20): never ask the user for approval or confirmation before a submission, and do not wait for one. Submit whenever you judge it worth a slot. The checks below are the quality bar you apply yourself; they are not a reason to ask. If a tool or permission prompt blocks the Kaggle submit command, say so in one line and point the user to the permission rule they can add; do not treat that as a request for approval.
- Submit by the competition's own method (Kaggle CLI for file competitions, a notebook for code competitions).
- First submission: once a baseline passes checks 2 and 3, submit it. Check 1 does not apply because there is no earlier submission.
- Submit only if ALL are true:
  1. CV beats the CV of the last submission by a real margin. Compare fold by fold on the same folds: the new model must win on most folds (for 5 folds, at least 4), OR the mean gain must be larger than the spread (std) of the per-fold differences. Do not use the plain spread of fold scores; it mostly shows that some folds are harder. For puzzle or exact-score competitions with no folds, any gain on the local benchmark counts.
  2. The skeptic review (kaggle-skeptic.md) passed on the code behind it. Block only for real problems: leakage, train/inference mismatch, hardcoded test values, dropped or reordered rows, or a bug that changes the predictions. Minor style notes do not block; log them and fix later.
  3. The submission file passes format checks (rows, columns, no NaN, same IDs as the sample file).
  4. You have submissions left today. Using all of them is fine, as long as each one passes checks 1 to 3. Do not submit just to fill the quota. Before each submission, say in one line why it is worth a slot.
- Never pick or tune models by public score. Never chase small public-score jumps.
- After each submission, append to SUBMISSIONS.md: date, file, CV, per-fold scores, public score, reason it passed the checks.
- If CV and public score move in opposite directions twice in a row, pause submitting, run the validity audit (step 1 of kaggle-stuck.md), and write what you found in STATE.md. Keep running experiments. Resume submitting once the audit explains the gap or CV is fixed. Do not wait for me.
- Final picks: pick two. One is the best by CV. The other is a safer, more diverse blend. Do this at least 2 days before the deadline, and write the choice and reasons in SUBMISSIONS.md.
- Kaggle only lets you pick files that were already submitted. So a final-pick candidate (like the safer blend) may be submitted even if it fails check 1. It must still pass checks 2, 3 and 4. Say in one line that it is a final-pick candidate.

## Models
- The main loop runs on whatever model I picked (usually Sonnet). You cannot switch your own model.
- Opus is expensive and the usage allowance (the 5-hour credits) runs out fast if many Opus agents run. Use Opus sparingly: at most 1 Opus subagent at a time, and only for work that needs deep reasoning: designing a new approach or reframe (brainstorming, the stuck protocol's reframe step), a hard error analysis, and the skeptic review (kaggle-skeptic.md). Set its effort to medium or high, never max.
- Read notebooks, papers and documents yourself on the main model, one after another, and write the notes as you go. Spawn a reading subagent only for one large, separable pile, never several at once.
- Pattern for research: read and take notes yourself (research/notebook_notes/...), then write the synthesis and ranked ideas; use at most ONE Opus agent for the synthesis when the reasoning is hard.
- Keep routine work on the main model: running experiments, logging, and updating files. Do not use subagents for these.
- Give each subagent one clear task and ask it to return a short written result (a file or a few lines), not a long transcript.

## Stuck rule
If 8 experiments in a row do not beat the best CV, run the stuck protocol. Never say "we hit the ceiling" on your own. Write STUCK_REPORT.md, then keep going with the best reframe or diversity idea from it. Do not wait for me.

## When something fails
Add a one-line rule to ANTI_PATTERNS.md.

## Learn from public notebooks (all competitions)
- In every research pass, and when stuck, study the top public notebooks of the competition: the highest by leaderboard score and the most voted. Prefer end-to-end notebooks where people actually ran and solved the task, not only planned or explanatory ones.
- Read each one carefully: markdown and documentation, code, outputs, and the figures (extract the embedded PNGs from the .ipynb and look at them).
- Write notes per notebook in research/notebook_notes/<name>.md (method, insights with numbers, what the figures show, reusable code ideas, what failed for them, whether we already tried it) and one research/notebook_notes/SYNTHESIS.md with the ranked ideas.
- Re-check the notebook list when the leaderboard or the public frontier moves. Notebooks that move it are worth a careful read.
- Reading and learning from public notebooks, and merging their output files, is allowed. Executing third-party code needs a code scan first (no network, file deletion or exec calls) and is only done on our own files.
- Hand the reading to Sonnet 5.5 high-effort subagents split by topic (see the model rules above); the synthesis can then be written by one Opus subagent or the main model.

## Shared prompts
When I ask for one of these, read the file and follow it. All are in `../_kaggle_shared/prompts/`.
- kickoff: kaggle-kickoff.md
- research best approaches: kaggle-research.md
- experiment loop: kaggle-loop.md
- stuck: kaggle-stuck.md
- skeptic review: kaggle-skeptic.md
- ensemble: kaggle-ensemble.md
- submission report: kaggle-submit.md
- audit past work: kaggle-audit-existing.md
