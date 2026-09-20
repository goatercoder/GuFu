#!/usr/bin/env bash
# Start Bulwark: create the virtualenv, install what is missing, build the UI, serve it.
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null; then
  echo "Python 3.11 or newer is required. Install it from https://www.python.org/downloads/" >&2
  exit 1
fi

if [ ! -d .venv ]; then
  echo "Creating the virtual environment..."
  "$PYTHON" -m venv .venv
fi
./.venv/bin/pip install -q -U pip
./.venv/bin/pip install -q -r backend/requirements.txt

if [ ! -f frontend/dist/index.html ]; then
  if command -v npm >/dev/null; then
    echo "Building the web interface (first run only)..."
    (cd frontend && npm install --no-audit --no-fund --silent && npm run build)
  else
    echo "Note: npm was not found, so the web interface was not built."
    echo "      The API still works at http://127.0.0.1:8800/api/docs"
  fi
fi

echo
echo "Bulwark is starting on http://127.0.0.1:8800"
echo "Press Ctrl+C to stop."
echo
cd backend && exec ../.venv/bin/python -m uvicorn bulwark.main:app --host 127.0.0.1 --port 8800
