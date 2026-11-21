# Chris Deotte: 2026 Playground AI workflow review

Research date: 2026-11-20. Author intended by the request: Chris **Deotte**, Kaggle `cdeotte`.

## Coverage and evidence limits

This is a sourced review of the five directly verified Deotte solution write-ups located for S6E3, S6E4, S6E5, S6E8 and S6E10. It is not a claim that all of his 2026 posts have been retrieved. Searches included his profile, episode-specific author queries, and AI/solution queries. Kaggle direct page opens returned empty bodies; search-indexed primary-page text supplied the readable material. Figures and linked code were not fully inspected. Numbers below are author reports, not independently reproduced experiments.

| Episode | Coverage |
|---|---|
| E1 | No Deotte solution write-up located. A separate Deotte pseudo-label discussion exists; not counted as a solution write-up. |
| E2 | No Deotte solution write-up located. Other authors thanking him are not his write-ups. |
| E3 | Verified first-place write-up; notes below. |
| E4 | Verified second-place write-up; notes below. |
| E5 | Verified second-place write-up; notes below. |
| E6 | No Deotte solution write-up located. A third-party “Merci Chris Deotte” write-up is not his. |
| E7 | No Deotte solution write-up located. |
| E8 | Verified first-place write-up; notes below. |
| E9 | E10 refers to a September discovery/win, but a direct E9 write-up was not located. Do not substitute another team's solution. |
| E10 | Verified first-place write-up, published November 1; notes below. |
| E11–E12 | No completed Deotte write-up verified at this research cutoff; December is future. |

Unlocated means unverified, not nonexistent. Recheck the [author profile](https://www.kaggle.com/cdeotte/writeups) and unresolved competition write-up indexes before calling this collection exhaustive.

## Reading notes

### S6E3 — 1st Place: GPT5.4, Gemini3.1, ClaudeOpus4.6 — KGMON Playbook

[Primary write-up](https://www.kaggle.com/competitions/playground-series-s6e3/writeups/1st-place-gpt5-4-gemini3-1-claudeopus4-6-kgm), March 31.

Deotte reports that agents wrote the solution code, trained 850 models, and ran 50 EDA scripts using four A100 GPUs. Agents investigated the relationship between original and synthetic data and proposed representations. The final architecture had feature-extraction models, GBDT/NN layers with nested OOF, and a regularized GPU logistic combiner. Diversity included architecture and representation changes; decimal digits and snapping synthetic values to original values were highlighted.

Proposed transfer: give agents a concrete modeling playbook and require evidence-driven EDA before another tuning campaign. Treat original-data provenance as a research question. For our budget, test a few distinct representations rather than reproducing his model count. These are hypotheses for our workflow, not measured gains.

### S6E4 — 2nd Place: Claude Code and Codex — GPU LogReg

[Primary write-up](https://www.kaggle.com/competitions/playground-series-s6e4/writeups/2nd-place-claude-code-and-codex-gpu-logreg), May 1.

Claude converted 150 March scripts for April. Deotte later combined Claude's conversion with Codex's independent conversion. A PyTorch linear layer implemented multinomial logistic regression, with balanced classes and coefficient regularization, for the balanced-accuracy metric. Extra work improved CV but reduced the selected private score versus the early solution.

Proposed transfer: maintain reusable model adapters with explicit metric, class-count, feature-schema and fold contracts. Validate converted scripts before training. Independent implementations can supply diversity, but their combination must pass local checks. More optimization can overfit selection; record search volume and keep a frozen comparison candidate. Do not assume the binary combiner is suitable for every task.

### S6E5 — 2nd Place: Autonomous Codex Yolo!

[Primary write-up](https://www.kaggle.com/competitions/playground-series-s6e5/writeups/2nd-place-autonomous-codex-yolo), June 1; includes author's comments.

The final blend used 218 level-one models, five-fold predictions and cuML logistic regression on logits; it did not use pseudo-labeling or deeper predictive stacking. Model generation included public-notebook adaptation, old-code conversion, model-specific campaigns, new families and architectural variants. Deotte's comment says he used a broad quality floor and genuine differences rather than seed-only copies.

Proposed transfer: distinguish standalone model improvement from contribution to the current ensemble. Preserve valid campaign intermediates and test their incremental value. Reproduce public single models on our folds when affordable. Avoid hard filtering solely to the highest standalone scores; use a predeclared quality floor plus held-out ensemble checks.

### S6E8 — 1st Place: Distributed Intelligence — NVIDIA Inference Hub

[Primary write-up](https://www.kaggle.com/competitions/playground-series-s6e8/writeups/1st-place-distributed-intelligence-nvidia-infe), August 31.

The workflow progressed from one autonomous agent to competing agents with shared knowledge, then additional LLM assistance. The initial agent built 380 models in four days, evaluating ensembles in batches. Later agents competed on single NN/XGB quality and exchanged discoveries. Packets of context and questions were sent to ChatGPT Pro; returned findings were incorporated. Further models were assigned work after assessment.

Proposed transfer: use compact research packets and a shared hypothesis/results ledger. Give independent reasoning attempts different questions, then exchange demonstrated findings. Preserve our existing agent and cost caps: this post does not establish that a large swarm is cost-effective for us. Start with one bounded second opinion only when authorized and useful.

### S6E10 — 1st Place: TFMs and LLMs with tabular data!

[Primary write-up](https://www.kaggle.com/competitions/playground-series-s6e10/writeups/1st-place-tfms-and-llms-with-tabular-data), November 1.

Deotte combined public OOF/test pairs with foundation models and GPT-based row classifiers. A target-first GPT estimated feature likelihood under each label, then applied Bayes' rule; target-last prediction supplied another view. He attributed the advantage to the synthetic generator and reported a 0.9624 AUC target-first model. He also flagged optimism from some public members early-stopping on scored folds.

Proposed transfer: distinguish AI writing experiments from an LLM trained as the predictive model. Investigate the generating process before expensive architectures. Treat target-first modeling as a synthetic-tabular hypothesis, not a universal recipe. In Enveda, a domain-specific spectrum/candidate representation is a more appropriate initial research direction. Audit public OOF provenance, not just row alignment.

## Comparison with our current shared strategy

Local sources reviewed: `rules.md`, `README.md` and all eight `prompts/kaggle-*.md` in this directory, plus the current Enveda STATE and experiment log. The following are proposed improvements, not experimentally validated conclusions. The current rule against unsupported conclusions should distinguish attributed literature observations and explicitly untested proposals from local experiment claims.

| Priority | Current behavior / gap | Proposed improvement | Acceptance evidence |
|---|---|---|---|
| P0 | Loop says keep an idea only if it beats the best; ensemble prompt first drops weak standalone models. | Separate “best single model” and “useful ensemble member” decisions. Keep a valid lower-scoring model if it improves the frozen ensemble on held-out checks. | Paired per-fold ensemble delta; compare both combiners refit on identical permitted rows. |
| P0 | OOF/test files are required, but metadata contracts are unspecified. | Add a prediction registry: run ID, source URL/version/license, code/data/fold hashes, row IDs, class order, output scale, early-stop policy, preprocessing lineage, runtime and cost. | Joining artifacts by ID reproduces stored scores; explicit mismatch failures. |
| P0 | Ordinary base OOF may be mistaken for an unbiased full-stack estimate. | Label scores as base OOF, conditional meta-CV, training/replay score, or fully nested validation. Use inner stopping/tuning or a separate stopping split for strict outer evaluation. | No scored outer labels enter fitting, stopping, feature selection or hyperparameter selection. |
| P1 | Reuse is informal. | Keep a small, tested adapter library and port checklist for old solutions. Revalidate external-data permissions and the new metric. | Same schema/fold contracts and a successful local smoke through inference. |
| P1 | “Change ONE thing” encourages controlled ablations but may constrain architectural exploration. | Allow a separately named reframe campaign with a frozen baseline, explicit budget and a single coherent hypothesis; ablate successful packages afterward. | Incremental benefit survives held-out comparison and useful components have logged ablations. |
| P1 | Stuck protocol triggers on eight standalone non-improvements. | Count both single-model and ensemble progress; schedule occasional representation research before reaching eight failures. | Ledger distinguishes failed single score from successful ensemble contribution. |
| P1 | Research source filter says skip anything AI-written. | Filter on traceable code, results and validation quality instead. AI authorship alone excludes exactly the agent work we want to study. | Every retained claim has inspectable primary evidence and stated limitations. |
| P1 | Research asks for 30 historical write-ups every pass. | Use an adaptive reading budget: closest cases first, summarize what changes the next experiment, broaden only when gaps remain. | Each recommended run has a cited hypothesis and cost estimate. |
| P2 | Campaigns and expensive ensemble fits have no common batch policy. | Run small family campaigns; retain diverse intermediates; refresh ensemble after a bounded batch or major representation change. | Cost and held-out gain logged per campaign, with a predeclared stop. |
| P2 | Sharing is via chat/STATE with no structured second-opinion packet. | Package task, metric, data dictionary, folds, best code, error slices, failed ideas, budget, and one concrete research question. | Returned proposals are checked locally before promotion. |

## Concrete prompt edits to consider

These are reviewable proposals; this research task does not change the live rules.

**kaggle-loop.md:** Replace “Keep an idea only if CV beats the best” with “Promote a single-model champion by paired fixed-fold CV. Independently retain a valid candidate if adding it improves the frozen ensemble under the same comparison protocol. Log both scores and the extra inference cost.”

**kaggle-ensemble.md:** Replace the unconditional standalone-score filter with a predeclared broad quality floor, provenance checks and contribution testing. Compare a regularized metric-appropriate combiner, a simple blend, and a nonlinear stack only when the validation and budget support it. A logistic model is suitable for class probabilities; MRR@25 needs candidate-aligned ranking outputs and validation of the resulting ranks.

**kaggle-research.md:** Replace the AI-written exclusion with evidence criteria. Add an original-data/generator investigation where relevant and a reusable-code search before new implementation. Avoid claiming a public notebook's score proves its validation is valid.

**rules.md:** Specify artifact metadata, validation score labels, campaign budgets and ensemble progress. Preserve fixed folds, local selection, existing account restrictions and spend limits.

## Suggested first use in Enveda

Do not launch a 200-model tabular campaign. The current experiment log has only an uninformative smoke score with near-singleton candidate sets, so first establish full candidate retrieval coverage and meaningful fixed-fold MRR@25. Then compare complementary retrieval/ranking representations and measure incremental ranking-ensemble value. Reuse the orchestration lessons while adapting predictive techniques to mass spectra.

No training, submissions, credential use, rentals or live-rule changes were performed for this review.
