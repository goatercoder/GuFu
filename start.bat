@echo off
rem GuFu launcher for Windows. Double-click this file. First run installs dependencies; later runs start instantly.
setlocal
cd /d "%~dp0"
set "CHECK=import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
set "PY="
py -3 -c "%CHECK%" >nul 2>&1 && set "PY=py -3"
if not defined PY python -c "%CHECK%" >nul 2>&1 && set "PY=python"
if not defined PY (
  echo Python 3.11 or newer was not found.
  echo Install it from https://www.python.org/downloads/windows/ and tick "Add python.exe to PATH" in the installer.
  goto :fail
)
if not exist ".venv\Scripts\python.exe" (
  echo Creating the Python environment - first run only...
  %PY% -m venv .venv || goto :fail
)
fc /b backend\requirements.txt .venv\requirements.installed >nul 2>&1
if errorlevel 1 (
  echo Installing dependencies - first run only, needs internet...
  .venv\Scripts\python.exe -m pip install --disable-pip-version-check -q -r backend\requirements.txt || goto :fail
  copy /y backend\requirements.txt .venv\requirements.installed >nul
)
cd backend
..\.venv\Scripts\python.exe -m gufu.launch
if errorlevel 1 goto :fail
exit /b 0
:fail
echo.
echo GuFu could not start. Please read the message above.
pause
exit /b 1
