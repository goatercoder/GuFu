@echo off
REM Start Bulwark on Windows: create the virtual environment, install, build the UI, serve it.
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python 3.11 or newer is required. Install it from https://www.python.org/downloads/windows/
  echo Remember to tick "Add python.exe to PATH".
  pause
  exit /b 1
)

if not exist .venv (
  echo Creating the virtual environment...
  python -m venv .venv
)
.venv\Scripts\python -m pip install -q -U pip
.venv\Scripts\python -m pip install -q -r backend\requirements.txt

if not exist frontend\dist\index.html (
  where npm >nul 2>nul
  if not errorlevel 1 (
    echo Building the web interface ^(first run only^)...
    pushd frontend
    call npm install --no-audit --no-fund --silent
    call npm run build
    popd
  ) else (
    echo Note: npm was not found, so the web interface was not built.
    echo       The API still works at http://127.0.0.1:8800/api/docs
  )
)

echo.
echo Bulwark is starting on http://127.0.0.1:8800
echo Close this window to stop it.
echo.
start "" http://127.0.0.1:8800
cd backend
..\.venv\Scripts\python -m uvicorn bulwark.main:app --host 127.0.0.1 --port 8800
