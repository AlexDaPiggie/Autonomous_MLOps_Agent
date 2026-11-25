# Shared Kaggle setup

The executable local supervisor is now available. See [OPERATING_GUIDE.md](OPERATING_GUIDE.md)
for installation, synthetic examples, migration, recovery, budget configuration and
current limitations. [IMPLEMENTATION_PROGRESS.md](IMPLEMENTATION_PROGRESS.md) records
preflight evidence, local commits and validation. Existing prompts/manual workflows
remain available. Controller execution is dry-run by default; paid providers and
network submissions are disabled. The legacy platform notes below describe the
manual workflow, and do not authorize spending or submissions under the controller.

Second upgrade (2026-11-24): real CSV/Parquet competitions with frozen folds, user-set
limits, `register-run` (log and independently score any run, including manual and Modal
work), an automatic code-writing mode (`start --mode code`), an optimization scorer plugin
and hill-climbing blends. See "Real competitions" in OPERATING_GUIDE.md.

- `rules.md`: the rules. Every competition's AGENTS.md points to it (CLAUDE.md imports AGENTS.md and rules.md). Edit it once and all competitions change.
- `prompts/`: the prompts (kickoff, research, loop, stuck, skeptic, ensemble, submit, audit). Ask Claude "run the stuck protocol" and it reads the file.

## New competition
1. Make the folder inside Coding.
2. Or run new_competition.bat Folder_Name <URL>. It writes AGENTS.md (canonical) and CLAUDE.md (imports it).
3. Start Claude Code or Codex there and say: "Follow kaggle-kickoff.md for <URL>".
4. Existing folders with only CLAUDE.md: move the URL and notes into a new AGENTS.md, then make CLAUDE.md just "@AGENTS.md" and "@../_kaggle_shared/rules.md". Not migrated automatically.

## Optional: real slash commands (/kaggle-stuck, /kaggle-research, ...)
Run this once in Windows Command Prompt:

mkdir "%USERPROFILE%\.claude\commands" & copy "%USERPROFILE%\Coding\_kaggle_shared\prompts\*.md" "%USERPROFILE%\.claude\commands\"

Run it again whenever you edit a prompt.

## Platform notes (per machine, not rules)
- Rules assume the agent can run Kaggle CLI, Modal, vastai and SSH without prompts, submit, and keep working unattended. Both agents can block on approvals.
- Claude Code: add allow rules in settings for these commands.
- Codex: default sandbox usually blocks network, so Kaggle CLI, Modal, vastai and SSH fail. Enable network in the workspace-write sandbox and set an approval policy that does not stall. Widening this lets an unattended agent spend money and submit; keep spend limits set on the provider side. Native Windows Codex has a weaker sandbox (WSL recommended). Verify Codex can read ../_kaggle_shared from a competition folder.
- Codex ignores @imports and does not read ~/.claude/CLAUDE.md. Put your global rules (no co-author lines, dash style, no venvs) in ~/.codex/AGENTS.md.
- If one agent's usage runs out, the other takes over only when you start it manually. Run "handoff" first.
- Slash-command copies below are Claude-only. With Codex, ask it to read the prompt file.

## Claude Pro + Modal defaults (2026-11-20)
- The LLM plan can be Claude Pro or a Codex plan; rules say "LLM plan".
- One main Claude session; optional bounded second opinions only when authorized. No mandatory reading/review swarms. Use Claude Pro; no automatic paid API/OpenRouter fallback. Checkpoint when Pro is unavailable.
- Claude designs a small campaign; a reusable Python runner executes it on Modal, saves predictions and structured results, then Claude reviews the summary.
- CONFIG.md defaults when no limits exist: $5 total GPU compute across Modal and Vast.ai per competition, $1 per campaign, one active GPU job, 30-minute invocation timeout. Explicit user settings and existing lower limits take precedence; count prior spend and reserve scheduled costs.
- Track standalone champions and useful ensemble members separately. Keep provenance in prediction_registry.jsonl and label validation scores precisely.
- Reviews cover material code changes and final candidates; unchanged reviewed runners reuse coverage.
- Existing local copies in ~/.claude/commands are separate files. Re-run the optional copy command above to refresh them; editing this shared directory does not synchronize those copies.
- Pre-edit versions are in _backups/claude_pro_modal_20261120_144333/.
- Modal is primary; Vast.ai automatically backs it up within the same GPU budget. Vast balance must be at least $2; destroy rented instances after results are retrieved.
