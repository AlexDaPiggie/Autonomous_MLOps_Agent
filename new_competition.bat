@echo off
set NAME=%~1
set URL=%~2
if "%NAME%"=="" (
  echo Usage: new_competition.bat Folder_Name https://www.kaggle.com/competitions/slug
  exit /b 1
)
set DIR=%~dp0..\%NAME%
if exist "%DIR%" (
  echo Folder already exists: %DIR%
  exit /b 1
)
mkdir "%DIR%"
> "%DIR%\AGENTS.md" echo # %NAME% Kaggle competition
>> "%DIR%\AGENTS.md" echo.
>> "%DIR%\AGENTS.md" echo At the start of every session, read ../_kaggle_shared/rules.md in full and follow it. Ignore _backups/.
>> "%DIR%\AGENTS.md" echo.
>> "%DIR%\AGENTS.md" echo ## This competition
>> "%DIR%\AGENTS.md" echo - URL: %URL%
>> "%DIR%\AGENTS.md" echo - Notes live in STATE.md and the experiment log.
> "%DIR%\CLAUDE.md" echo @AGENTS.md
>> "%DIR%\CLAUDE.md" echo @../_kaggle_shared/rules.md
echo Created %DIR%
echo Next: open Claude Code or Codex in that folder and say: start
