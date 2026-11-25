@echo off
setlocal DisableDelayedExpansion
rem Use "python" if it is on PATH, otherwise the Windows "py" launcher.
where python >nul 2>nul
if %errorlevel%==0 (
  python "%~dp0kaggle_agent\initialize.py" %*
) else (
  py -3 "%~dp0kaggle_agent\initialize.py" %*
)
exit /b %errorlevel%
