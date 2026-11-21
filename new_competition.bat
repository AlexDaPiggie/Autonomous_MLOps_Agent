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
> "%DIR%\CLAUDE.md" echo # %NAME% Kaggle competition
>> "%DIR%\CLAUDE.md" echo.
>> "%DIR%\CLAUDE.md" echo @../_kaggle_shared/rules.md
>> "%DIR%\CLAUDE.md" echo.
>> "%DIR%\CLAUDE.md" echo ## This competition
>> "%DIR%\CLAUDE.md" echo - URL: %URL%
>> "%DIR%\CLAUDE.md" echo - Notes live in STATE.md and the experiment log.
echo Created %DIR%
echo Next: open Claude Code in that folder and say: start
