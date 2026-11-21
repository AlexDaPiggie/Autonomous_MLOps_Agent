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
