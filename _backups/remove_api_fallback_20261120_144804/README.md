# Shared Kaggle setup

- `rules.md`: the rules. Every competition's CLAUDE.md imports it. Edit it once and all competitions change.
- `prompts/`: the prompts (kickoff, research, loop, stuck, skeptic, ensemble, submit, audit). Ask Claude "run the stuck protocol" and it reads the file.

## New competition
1. Make the folder inside Coding.
2. Copy any competition's CLAUDE.md into it. Change the title and the notes lines.
3. Start Claude Code there and say: "Follow kaggle-kickoff.md for <URL>".

## Optional: real slash commands (/kaggle-stuck, /kaggle-research, ...)
Run this once in Windows Command Prompt:

mkdir "%USERPROFILE%\.claude\commands" & copy "%USERPROFILE%\Coding\_kaggle_shared\prompts\*.md" "%USERPROFILE%\.claude\commands\"

Run it again whenever you edit a prompt.

## Claude Pro + Modal defaults (2026-11-20)
- One main Claude session; optional bounded second opinions only when authorized. No mandatory reading/review swarms. Claude Pro is primary; paid API/OpenRouter is an automatic backup with a separate $10 cumulative competition cap.
- Claude designs a small campaign; a reusable Python runner executes it on Modal, saves predictions and structured results, then Claude reviews the summary.
- CONFIG.md defaults when no limits exist: $5 total GPU compute across Modal and Vast.ai per competition, $1 per campaign, one active GPU job, 30-minute invocation timeout. Explicit user settings and existing lower limits take precedence; count prior spend and reserve scheduled costs.
- Track standalone champions and useful ensemble members separately. Keep provenance in prediction_registry.jsonl and label validation scores precisely.
- Reviews cover material code changes and final candidates; unchanged reviewed runners reuse coverage.
- Existing local copies in ~/.claude/commands are separate files. Re-run the optional copy command above to refresh them; editing this shared directory does not synchronize those copies.
- Pre-edit versions are in _backups/claude_pro_modal_20261120_144333/.
- Modal is primary; Vast.ai automatically backs it up within the same GPU budget. Vast balance must be at least $2; destroy rented instances after results are retrieved. API backup spend never resets on handoff/provider changes.
