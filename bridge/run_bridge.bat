@echo off
REM ── Barrel Terminal — Bloomberg live-price bridge (one-click launcher) ──
REM 1. Install Python 3 from python.org (tick "Add python.exe to PATH").
REM 2. Double-click this file. First run installs dependencies automatically.
REM 3. Keep the Bloomberg Terminal + your live price workbook open.

cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (set PY=py -3) else (set PY=python)

echo Installing/updating dependencies...
%PY% -m pip install --quiet --upgrade -r requirements.txt

if not exist bridge_config.json (
  echo.
  echo  bridge_config.json not found.
  echo  Copy bridge_config.example.json to bridge_config.json and paste your token.
  echo.
  pause
  exit /b 1
)

echo Starting bridge...  (close this window to stop)
%PY% bloomberg_bridge.py
pause
