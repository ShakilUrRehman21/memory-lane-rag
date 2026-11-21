@echo off
setlocal
cd /d "%~dp0"
title Memory Lane - API key check
if not exist ".venv\Scripts\python.exe" (
  echo Run start.bat once first so everything gets installed.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" backend\check_keys.py
echo.
pause
