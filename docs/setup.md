# Setup help and extra commands

[Back to the quick start](../README.md)

## Optional packages

Run these from `_kaggle_shared` when your experiment needs them:

```powershell
python -m pip install -e ".[boosting]"     # CatBoost, LightGBM, XGBoost
python -m pip install -e ".[parquet]"      # Parquet files
python -m pip install -e ".[optimization]" # OR-Tools
```

## Optimization competitions

Optimization needs a Python scorer that implements `score(solution_path, data_dir)` and rejects invalid solutions. Prepare it from the competition's scoring rules, then use its actual path below:

```powershell
ka new https://www.kaggle.com/competitions/COMPETITION-SLUG --optimization --scorer C:\path\scorer.py --solution-name submission.csv --direction minimize
```

Use `maximize` instead if a higher score is better. See [scorer setup](../OPERATING_GUIDE.md#real-competitions-second-upgrade-2026-11-24) for data files and manual initialization.

## More commands

Run inside the competition folder, or add `--dir C:\path\competition` to a `ka` command.

| Task | Command |
|---|---|
| Read public notebooks and discussions | `ka research` |
| View agent settings | `ka agent` |
| Set Claude effort | `ka agent claude --effort high` |
| Set Codex effort | `ka agent codex --effort high` |
| Compare a run with the champion | `ka diff RUN-ID` |
| Copy a saved solver/trainer | `ka restore champion` |
| See subscription sessions | `ka usage` |
| Enable / disable automatic submissions | `ka submit --auto on` / `ka submit --auto off` |
| Submit a particular run | `ka submit RUN-ID` |
| Inspect resource limits | `python -m kaggle_agent limits` |
| Blend saved predictions | `python -m kaggle_agent blend --competition .` |
| Check installed tools | `python -m kaggle_agent doctor` |

`ka go` also collects public research when due. Research is read as evidence, never executed as downloaded code. Automatic submissions can send a new champion after a campaign; turn them off if you want to review every submission yourself.

## Cloud GPUs (optional)

**The automatic loop runs locally.** There is no `ka cloud` command or automatic Modal/Vast job launcher. You can train manually on cloud GPUs and bring the results back.

1. Set up [Modal](https://modal.com/docs/guide) or [Vast.ai](https://docs.vast.ai/) using its own guide. Configure your spending limit there.
2. Train with the same row IDs, target encoding, and frozen validation folds in `.kaggle-agent/folds.csv`. Fit preprocessing only on each training fold.
3. Download `oof.csv` and `test.csv` and the exact code that produced them. OOF means each training row was predicted by a model that did not train on that row.
4. From the competition folder, register the files:

```powershell
python -m kaggle_agent register-run --competition . --oof out\oof.csv --test out\test.csv --code train.py --hypothesis "cloud GPU experiment"
ka status
```

Prediction CSVs need an `id` column and `pred`, or `pred_0`, `pred_1`, etc. for multiclass predictions. [Full output contract](../OPERATING_GUIDE.md#3a-manual-work-stays-the-main-engine-register-every-run).

For optimization, import a solution instead:

```powershell
python -m kaggle_agent register-run --competition . --solution submission.csv --code solve.py --hypothesis "cloud solver"
```

Cloud billing is separate from your coding-agent subscription. Stop rented instances after retrieving results. Importing a result does not submit it to Kaggle.

## Troubleshooting

| Problem | Next step |
|---|---|
| `python` or `git` not found | Reopen PowerShell after installation; check the installer's PATH option. |
| `ka` not found | Use `python -m kaggle_agent.ka` instead. Use the same Python that installed this project. |
| Kaggle refuses a download | Check your token file and accept the competition rules on Kaggle. |
| Agent asks you to sign in | Run `claude` and `/login`, or `codex login`; then `ka go`. |
| Plan usage limit reached | Wait for the plan reset, then `ka go`. |
| `memory_limit` or timeout | Inspect the latest `.kaggle-agent/sessions/` folder and `outcome.json`; use `ka setup` to adjust limits within your computer's capacity. |
| Need every available option | Run `ka --help` or `ka COMMAND --help`. |

## Prefer the manual prompt workflow?

The automatic loop is the beginner path. For manual sessions, use [the prompts](../prompts/) and [shared rules](../rules.md). In a competition folder, `AGENTS.md` holds its instructions; `CLAUDE.md` imports only `AGENTS.md`. [Preserved manual notes](legacy-workflow.md).
