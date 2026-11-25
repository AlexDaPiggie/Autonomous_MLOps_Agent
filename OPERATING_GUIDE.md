# Operating the local Kaggle supervisor

This implementation adds a local control plane around the existing prompt workflow.
It does not run a cloud service. All development used mocks and synthetic data, with
zero paid jobs/inference, submissions or remote pushes. Historical competition
folders, backups, and manually authored handoffs are preserved.

## Everyday use: `ka` (2026-11-24)

`ka` wraps everything below into short commands. Run them from inside the
competition folder (except `setup` and `new`).

| Command | What it does |
|---|---|
| `ka setup` | Once. Checks Claude/Codex/Kaggle CLIs, asks agent, CPU threads, RAM, hours per run, campaigns/trials, phone alerts (ntfy or Telegram). Saves `~/.kaggle-agent/settings.json` and limits. Confirms you use your existing plan (paid APIs stay blocked). |
| `ka new <url>` | Creates the folder (AGENTS.md/CLAUDE.md), downloads and unzips the data, detects train/test/sample files, ID, target, task and the metric (from Kaggle), asks you to confirm, freezes folds, asks if you read the rules and whether to turn on auto-submit. Optimization: `ka new <url> --optimization --scorer my_scorer.py --solution-name submission.csv`. |
| `ka go` | Starts or resumes the code-writing loop with your saved settings. Prints one block per trial (idea, screen/full scores, outcome), blends after each campaign, auto-submits a new best run if auto-submit is on, sends phone alerts. Ctrl+C or `ka stop` stops safely. |
| `ka status` | Best CV, recent runs, champions, submissions with public scores, deadline and final-pick reminder. |
| `ka dash` | Opens `.kaggle-agent/views/dashboard.html`: score chart, recent runs, branches, submissions. Reloads every 30 s; rebuilt after every run. Read-only. |
| `ka submit [run-id]` | Builds the file in the sample_submission format from the best run (or a given run), checks columns/IDs/values, shows CV and quota, asks y/n (`--yes` skips), sends with the Kaggle CLI and logs it. |
| `ka submit --auto on/off` | Auto-submit: after each campaign with a new champion, sends the best run once if the daily limit allows, always keeping 1 slot for you. Uses CV only; public scores are shown, never used. |
| `ka stop`, `ka usage` | Safe stop; agent sessions per day and limit hits. |

Submission files: probabilities for roc_auc/log_loss binary columns, one column per class
when the sample has per-class columns, three space-separated labels for map3, labels for
accuracy-type metrics, raw values for regression, the solution file for optimization.
Kaggle's CLI cannot select final submissions: in the last two days `ka status` reminds you to
pick the best-CV submission plus one different-model hedge on the website.
Submission settings live in `.kaggle-agent/submission.json`; changing them never changes the
frozen profile. Profile notes (deadline, target_score, rules_reviewed) may be edited; task,
metric, data and folds may not.

## Real competitions (second upgrade, 2026-11-24)

This section supersedes older notes below that call real data conversion a manual
step or say agents are read-only. Everything here runs locally; nothing submits to
Kaggle or starts paid compute.

### 1. Freeze the competition once
Tables (classification/regression; forecasting = regression with time folds):

    python -m kaggle_agent init --competition "C:\path\Comp" --task classification ^
      --train data\train.csv --test data\test.csv --id id --target y --metric roc_auc --folds 5
    (add --group col for grouped data, --time col for time order)

This writes `.kaggle-agent/folds.csv` (frozen; never overwritten) and `profile.json`.
Metrics: log_loss, roc_auc, accuracy, balanced_accuracy, map3, rmse, mae, rmsle, r2, mape.
Optimization (Santa-style): write a `scorer.py` with `score(solution_path, data_dir) -> float`
that raises on infeasible solutions, then:

    python -m kaggle_agent init --competition "C:\path\Santa" --task optimization ^
      --scorer my_scorer.py --files data\cities.csv --solution-name submission.csv --direction minimize

Then read the competition rules and set `"rules_reviewed": true` in profile.json
(optional: `"deadline"` with timezone, `"target_score"` = top public LB score, shown to
the agent for orientation only). Changing train/test/folds/scorer later is detected and
blocks runs.

### 2. Set your limits (optional)

    python -m kaggle_agent limits                       # show current limits and machine ceilings
    python -m kaggle_agent limits --configure limits.json

limits.json example: `{"seconds": 7200, "memory_mb": 8192, "threads": 4, "max_iterations": 20000,
"agent_seconds": 900, "screen_fraction": 0.25, "smoke_rows": 2000}`. Ceilings: 12 h per run,
75% of RAM, your CPU thread count, 100k iterations.

### 3a. Manual work stays the main engine: register every run
Any script (local or Modal) that writes `oof.csv` and `test.csv` (column `id` plus `pred`, or
`pred_0..pred_K-1` in class order) can be logged and independently scored:

    python -m kaggle_agent register-run --competition "C:\path\Comp" ^
      --oof out\oof.csv --test out\test.csv --code train.py features.py --hypothesis "lgbm + ratio features"
    python -m kaggle_agent blend --competition "C:\path\Comp"     # stacker vs hill climbing, meta-CV

The run's code and outputs are copied to `.kaggle-agent/runs/<id>/`. Duplicate code+config is
rejected, dropped OOF rows are rejected, and only a paired fold improvement becomes champion.
Optimization: `register-run --solution submission.csv --code solve.py`; the best solution is kept
in `.kaggle-agent/best/` and only replaced by a strictly better scored file.
Scripts can use `from kaggle_agent import toolkit as kt` (`kt.load()`, `kt.splits()`, `kt.save()`,
`kt.tune()`); set the KA_* variables or let the supervisor set them.

### 3b. Automatic code mode: the agent writes the scripts

    python -m kaggle_agent start --competition "C:\path\Comp" --mode code --agent claude ^
      --execute --subscription-confirmed --campaigns 3 --trials 4

Each trial: the agent gets a brief (data summary, independently scored results, branch to
pursue, stored lessons, recent failures, the champion's code in `./champion/`) and writes
`train.py`/`solve.py` in `.kaggle-agent/workspace/<trial>/`. The supervisor then:
blocks obvious rule breaks (submission, Modal/Vast, credentials, supervisor files) -> smoke run on
a tiny sample (up to two repair rounds) -> screen run on `screen_fraction` of rows -> full run
-> independent scoring -> champion check -> lessons saved. After each campaign it tries a blend.
The screen only blocks a full run after four screen/full pairs agree (Spearman >= 0.5); if they
disagree, screens stop. Claude runs with edit permission only (no shell); Codex runs in its
workspace-write sandbox. Agents run as your Windows user: the static checks are guard rails, not a
sandbox. `python -m kaggle_agent doctor` checks the CLI flags the adapters use.
`python -m kaggle_agent usage` shows agent sessions per day, limit hits and reported tokens.

### 3c. Propose mode on real tables
`start --execute` without `--mode code` still works: the agent (or the default cycle) picks
documented model families/hyperparameters (`lightgbm` with learning_rate, num_leaves, ... up to
`max_iterations`), with `seeds` (multi-seed average) and `full_refit` (test from a 100% refit).

### Benchmark
`python -m kaggle_agent benchmark --realistic` compares propose and code mode end to end on a
6,000-row synthetic CSV competition (see benchmark-results/realistic-benchmark.json). The code
mode uses two hand-written scripts through a mock coder: it shows what each mode can express,
not how good a real LLM is.

## Install and verify

Run from the shared repository in PowerShell, with Python 3.11 or later:

```powershell
python -m pip install -e ".[models]"
python -m kaggle_agent doctor
python -m unittest discover -v
```

The control plane uses SQLite, Git and psutil. Model dependencies are optional and
loaded on demand. The inspected machine already had the required CPU libraries;
development did not install packages or create environments. Optional extras are
`boosting`, `search`, `forecast`, and `optimization`. Installing an extra does not
select a model or launch anything. The forecasting extra is for custom/manual
pipelines; built-in forecasters are seasonal naive and lag ridge/boosting.

`doctor` only queries CLI versions, never inference/auth tokens. Verified locally:
Python 3.12.10, SQLite 3.49.1, Codex 0.164.0, Claude Code 2.1.330. CLI protocols are
validated locally; real authenticated inference was not tested. No bypass-permission
flags or automatic alternate providers/subscriptions are used.

## Try the complete local path without competition data

```powershell
$demo = Join-Path $env:TEMP 'kaggle supervisor demo'
New-Item -ItemType Directory -Path $demo
python -m kaggle_agent init --competition "$demo" --task regression --demo
python -m kaggle_agent start --competition "$demo" --agent mock
python -m kaggle_agent start --competition "$demo" --agent mock --execute --trials 2
python -m kaggle_agent status --competition "$demo"
python -m kaggle_agent report --competition "$demo"
python -m kaggle_agent stop --competition "$demo"
python -m kaggle_agent resume --competition "$demo" --agent mock --execute
```

Use a fresh directory: initialization refuses an existing profile. `--demo` generates
a tiny synthetic dataset and marks only that fixture's rules reviewed. Supported
tasks: classification, regression, optimization, forecasting. Plain `start` is a
dry-run: no child or inference launch. `--execute` runs bounded CPU children. Default
one campaign, one hypothesis; `--campaigns 1..20`, `--trials 1..4` bound each invocation.
The default 60-second/1024-MB cap is per child, with an absolute 1800-second/2048-MB
ceiling; stricter profile limits win. A campaign can include multiple fidelity jobs
and an ensemble assessment. Memory caps are monitored RSS limits, not an OS sandbox.

Each tabular trial follows selected-model synthetic smoke, screen (2 boosting
iterations), intermediate (10), full (configured iterations), then a compatible
library assessment when two base candidates exist. Screening uses the same fixed
folds/data in this first implementation, reducing model iterations rather than
silently changing validation. Linear models may have identical fidelity scores.
Screening is currently a correctness/resource check, not an aggressive elimination
heuristic; no low-fidelity score can promote. Exploration is preserved. Optimizers
screen at 10/30 search iterations. Forecasting follows the same frozen origins.

All completed base predictions remain available, including weaker challengers.
Standalone and ensemble champions are separate. A challenger must beat the paired
fold policy, with comparable metric/data/split/evaluator and score type. The ensemble
gate compares conditional meta-CV against a single-base combiner refitted on the same
permitted rows. Conditional meta-CV is not independent full-pipeline validation.
`evaluation/nested.py` offers fixed-library nested stacking for stricter offline
assessment, with all base fitting inside each outer training split. It is opt-in
because it requires substantially more fits.

## Adopt an existing competition non-destructively

First inspect and archive its history:

```powershell
python -m kaggle_agent audit --competition 'C:\path with spaces\competition'
python -m kaggle_agent migrate --competition 'C:\path with spaces\competition'
python -m kaggle_agent migrate --competition 'C:\path with spaces\competition' --apply
python -m kaggle_agent init --competition 'C:\path with spaces\competition' --task classification
```

`migrate` defaults to dry-run. Applying backs up SQLite using its backup API, then
archives supported STATE/CONFIG/experiment/leaderboard/registry files verbatim with
checksums in one transaction. Repeat imports are idempotent. Changed versions are
retained as conflicts, never overwritten. Diagnostic/ambiguous legacy scores are
not turned into full-validation records or champions. Missing metadata stays unknown.
There is no destructive schema migration: schema v1 is explicit and unknown versions
are rejected. Preserve the `.before-import-*.bak` files for recovery.

Review `.kaggle-agent/profile.json` and supply `.kaggle-agent/dataset.json` before
first registration. `rules_reviewed` starts false for real data. Review competition
AI/external-data rules, metric/direction, constraints, deadline with timezone,
validation, baseline, existing spend and outstanding jobs. Where CONFIG/STATE exist,
`legacy_limits_reviewed` also starts false. Set it true only after review; include
stricter runtime/RSS values in `constraints.seconds`/`constraints.memory_mb`. Paid
execution remains unavailable even after review. Do not run sibling GPU scripts as
a fallback around these gates.

The JSON data contract is intentionally explicit:

- Tabular: `task`, unique `ids`, feature matrix `X`, encoded numeric `y`, fixed
  `folds`, unique `test_ids`, and `test_X`; optional `categorical` column indices.
  Classification labels must be 0..K-1 and every training fold must include classes.
- Optimization: `task: optimization`, nonnegative `weights`, `values`, `capacity`.
  The built-in reference solver is knapsack. Other problem objectives/constraints
  need a reviewed adapter and independent checker; no claim of a generic optimizer.
- Forecasting: `task: forecasting`, ordered unique `times`, `values`, nonoverlapping
  `origins`, `horizon`, `season`. No scored future values are used as lag features.

Use `dataset_identity(data)` from `kaggle_agent.__main__` to obtain `data_hash` and
`split_hash` for the reviewed profile. The immutable file checksum also covers the
feature/test data. Real CSV/Parquet conversion remains an explicit manual step;
the JSON reference runner loads data in memory, so large competitions need a
reviewed streaming/native data adapter. Existing stronger native runners remain
available manually, without automatic migration.

Profile changes after registration fail closed. To create a materially new validation
version, use a separate competition workspace/profile, preserving the old DB/history;
do not edit SQLite to mix old/new champions. Evaluator/source changes invalidate old
comparisons. Completed legacy jobs must be reviewed rather than blindly relaunched.

New manual competitions can still use:

```powershell
.\new_competition.bat "Folder With Spaces" "https://www.kaggle.com/competitions/slug"
.\new_competition.bat "Another Folder" "https://www.kaggle.com/competitions/slug" --automation
```

The wrapper now uses Python to avoid batch echo/URL expansion problems. It creates
canonical AGENTS.md and CLAUDE.md with relative imports, refuses existing folders,
and optionally creates a disabled profile. Python is now needed for this initializer.

## Configuration, memory and research

An optional `--config path.json` supplies a JSON model configuration:

```json
{"seed":42,"metric":"rmse","family":"linear","parameters":{"alpha":1.0},"options":{"interactions":false,"target_log":false}}
```

With multiple trials, the built-in small portfolio tries linear/forest/hist families,
optimization operators or forecast representations, varying seeds deterministically.
Explicit single-trial configs select CatBoost/LightGBM/XGBoost if installed. Calibration
uses inner training CV; categorical preprocessing and target transforms fit within
each training fold. `fold_target_encode` deliberately accepts no validation labels.
Time-aware tabular tasks should use the rolling forecasting path, not random CV.

Research APIs are `Portfolio.add/update/rank`, `Knowledge.add/search/outcome`, and
`review_stagnation`. FTS summaries carry provenance/license/evidence/conditions/risk,
and searches prioritize own discoveries, including failed ideas. External-data-required
findings are excluded unless explicitly allowed. No source is downloaded or executed
automatically. No peer source was copied, so no unverified license was inherited.
The CLI seeds three directions, records experiment branch/parent relationships and
uses a 25% exploration turn. Heuristic estimates are not empirical gain guarantees.
Eight completed full own-pipeline trials without standalone/ensemble progress produce
an attributed local research-review artifact and a checkpoint boundary. Execution
failures and screening runs do not increment that counter. New configuration/code
and interpretation of weak segments remain research work, not blind retries.

Working task, recent experiments, strategic branches and cross-task retrieval form
four memory layers. Rotation records a compact checkpoint at campaign boundaries;
it does not reset spend/jobs. Raw logs/history stay on disk/SQLite. Human STATE.md is
never replaced. Generated compatible views are under `.kaggle-agent/views/`:

```powershell
python -m kaggle_agent checkpoint --competition 'C:\path\competition'
python -m kaggle_agent export --competition 'C:\path\competition'
```

`execution.efficiency` provides bounded deterministic/optional Optuna search, fidelity
rank agreement and checksum-protected caches keyed by data/split/config/code/seed/
evaluator. These utilities are available to reviewed campaign code; Optuna tuning and
large cache reuse are not automatically enabled for every CLI run.

## Budget and permissions

One default ledger is `%USERPROFILE%\.kaggle-agent\global.sqlite3` across competitions.
`--db path` or `KAGGLE_AGENT_HOME` isolates development fixtures; never create separate
production ledgers to evade the global cap. Defaults: 4000 cents/month, 500 reserve,
500 lifetime competition, 100 campaign, 100 invocation, one paid concurrent reservation.
Fixed costs/period are unconfirmed. Lower configured caps cannot be raised by this CLI.

```powershell
python -m kaggle_agent budget
python -m kaggle_agent budget --configure 'C:\private\reviewed-budget.json'
python -m kaggle_agent budget --record-charge 'C:\private\invoice-line.json'
```

Copy `config/budget.example.json`, fill actual subscription/fixed expenses including
taxes and the UTC billing cycle (`billing_day` 1..28), and review before setting
`confirmed: true`. Record storage, failed compute, inference, tax and unreported
charges with unique invoice IDs using the charge example. Do not count a subscription
both in recurring `fixed_cents` and as an actual ledger line. Multiple provider cycles
should use a conservative common monthly envelope; reconcile each invoice explicitly.
Uncertain/stale reservations remain charged, even across rollover. Only authoritative
actual charges release them. Overruns are recorded and invalidate confirmation. Caps,
concurrency and reservations are atomic; 50/75/90% warnings appear in budget summaries.
Delayed provider billing cannot provide an absolute external-spend guarantee.

Real CLI adapters are opt-in, research-only (Codex read-only sandbox; Claude plan
mode). They preserve user-selected subscriptions, never fall back to paid inference:

```powershell
python -m kaggle_agent start --competition 'C:\path\competition' --agent codex --execute --subscription-confirmed
```

This requires confirmed global fixed costs and a verified subscription CLI setup.
Do not use this flag for an API-billed configuration. Metered-provider environment
variables block adapter invocation. CLI configuration/auth type is not independently
attested, and processes share the user's OS identity: use credential isolation for
any future stronger automation. Adapters currently provide bounded advisory sessions;
they can propose bounded hypothesis/config objects, which pass the same gates before
use. They do not autonomously rewrite shared source or execute research text. Human coding
agent workflows are retained for implementing new pipelines. Session limits checkpoint
and wait; a different agent is selected only explicitly by the user.

Modal/Vast launch and network submission functions always reject. There is no CLI
switch that enables them. Enabling either requires a separately authorized isolated
broker/backend implementation and review of billing/rules. Submission file validators
still check schema, ID order, finite values, bounds, constraints, eligibility, quota
and explicit authorization locally. No real submission was made or tested.

## Recovery and rollback

`stop` persists an immediate stop request. The active watchdog observes it and kills
the local process tree while preserving partial artifacts/logs. Ctrl+C does the same.
`resume --execute` is explicit after a stop. Every local worker retains its own time
and RSS guard if its supervisor dies. Process leases heartbeat; a replacement waits
for expiry and reconciles recorded PID plus creation time, preventing PID-reuse kills.
An active job is never duplicated. Ambiguous provider intent blocks until reconciled;
there is no guessed retry or automatic provider fallback.

An invalid/partial artifact cannot promote. Inspect the job's worker.log, status.json,
result/manifest and DB events. Failed equivalent fingerprints cannot silently rerun;
use a materially changed reviewed config/code (record why), preserving original evidence.
The recovery policy caps ordinary retries at three and backs off; the reference CLI
fails closed rather than automatically retrying a failed training configuration.

Status/stop/export still work after a deadline or profile edit. Launch rechecks the
deadline. Leases use host wall clock; do not run simultaneous supervisors on separate
machines against an unsynchronized shared SQLite file. No daemon is installed.

Back up SQLite with `Store.backup(destination)` and copy associated job artifacts
before a migration. To roll back source changes, review and revert individual local
implementation commits. Do not reset/clean repositories or delete competition history.
Do not remove the global ledger to reset spend. `_backups/` is unchanged.

## Benchmark and evidence limits

```powershell
python -m kaggle_agent benchmark --output benchmark-results
```

Eight synthetic tasks (two seeds per domain), two bounded trials per variant, compare
a simple baseline proxy against challengers with incumbent retention. The original
repository had no executable agent runner; this is not a measured original-vs-upgraded
agent contest. Results include raw rejected challenger scores, times, configs and
unavailable token metrics (`null`). Historical eight-task runs, peer ablations and live
private leaderboard/medal evidence require separately prepared authorized datasets and
agent access; none are claimed. Synthetic reliability tests establish controlled
invariants, not real provider behavior or a guarantee of medals at $40/month.
