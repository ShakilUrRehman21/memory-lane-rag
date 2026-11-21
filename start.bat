@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Memory Lane

if "%~1"=="__open" goto :open_browser
if not defined PORT set "PORT=8000"

echo.
echo   ==========================================
echo      Memory Lane
echo   ==========================================
echo.

call :setup || goto :failed
if "%~1"=="__setup" exit /b 0

echo   Starting Memory Lane at http://127.0.0.1:%PORT%
echo   Keep this window open while you use it. Close it (or press Ctrl+C) to stop.
echo.
start "" /b cmd /c call "%~f0" __open
".venv\Scripts\python.exe" backend\run.py
echo.
echo   Memory Lane has stopped.
pause
exit /b 0


:setup
rem ---- Python ----------------------------------------------------------
if exist ".venv\Scripts\python.exe" goto :python_ready
echo   [1/4] Creating the Python environment (first run only)...
where py >nul 2>nul && (py -3 -m venv .venv) || (python -m venv .venv)
if not exist ".venv\Scripts\python.exe" (
  echo.
  echo   Python 3.10 or newer is required. Install it from https://www.python.org/downloads/
  echo   and tick "Add python.exe to PATH" during setup, then run this file again.
  exit /b 1
)
:python_ready
fc /b requirements.txt ".venv\installed-requirements.txt" >nul 2>nul && goto :python_deps_ready
echo   [2/4] Installing Python packages (this can take a few minutes the first time)...
".venv\Scripts\python.exe" -m pip install --upgrade pip -q
".venv\Scripts\python.exe" -m pip install -r requirements.txt -q || exit /b 1
copy /y requirements.txt ".venv\installed-requirements.txt" >nul
:python_deps_ready

rem ---- Web app ---------------------------------------------------------
where npm >nul 2>nul
if errorlevel 1 (
  if exist "frontend\dist\index.html" goto :web_ready
  echo.
  echo   Node.js is required to build the app the first time.
  echo   Install the LTS version from https://nodejs.org/ and run this file again.
  exit /b 1
)
fc /b frontend\package.json "frontend\node_modules\.installed-package.json" >nul 2>nul && goto :node_deps_ready
echo   [3/4] Installing web app packages...
pushd frontend
call npm install --no-audit --no-fund --loglevel=error || (popd & exit /b 1)
copy /y package.json "node_modules\.installed-package.json" >nul
popd
:node_deps_ready
echo   [4/4] Building the web app...
pushd frontend
call npx vite build --logLevel error || (popd & exit /b 1)
popd
:web_ready

rem ---- Settings --------------------------------------------------------
if not exist ".env" copy ".env.example" ".env" >nul
exit /b 0


:open_browser
rem Wait until the server answers, then open the browser.
if not defined PORT set "PORT=8000"
for /l %%i in (1,1,90) do (
  curl -s -o nul "http://127.0.0.1:%PORT%/api/health" && (start "" "http://127.0.0.1:%PORT%" & exit /b 0)
  timeout /t 1 /nobreak >nul
)
exit /b 0


:failed
echo.
echo   Setup did not finish. Scroll up to see what went wrong.
pause
exit /b 1
