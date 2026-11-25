@echo off
setlocal DisableDelayedExpansion
python "%~dp0kaggle_agent\initialize.py" %*
exit /b %errorlevel%
