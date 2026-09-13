#!/usr/bin/env bash
# GuFu launcher for Linux (and macOS via start.command). First run installs dependencies; later runs start instantly.
set -u
cd "$(dirname "$0")" || exit 1

fail() { echo; echo "ERROR: $*"; echo; read -rp "Press Enter to close this window..." _; exit 1; }

CHECK='import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'
PY=""
for c in python3.13 python3.12 python3.11 python3 /opt/homebrew/bin/python3 /usr/local/bin/python3 \
         /Library/Frameworks/Python.framework/Versions/3.*/bin/python3; do
  p=$(command -v "$c" 2>/dev/null) || continue
  # On macOS, /usr/bin/python3 without the Xcode command-line tools is a stub that pops up an installer; skip it.
  if [ "$p" = /usr/bin/python3 ] && command -v xcode-select >/dev/null 2>&1 && ! xcode-select -p >/dev/null 2>&1; then continue; fi
  if "$p" -c "$CHECK" 2>/dev/null; then PY="$p"; break; fi
done
[ -n "$PY" ] || fail "Python 3.11 or newer was not found.
Install it from https://www.python.org/downloads/ and then run this again."

if [ ! -x .venv/bin/python ] || ! .venv/bin/python -c "import sys" >/dev/null 2>&1; then
  echo "Creating the Python environment (first run only)..."
  rm -rf .venv
  "$PY" -m venv .venv || fail "Could not create .venv (on Debian/Ubuntu: sudo apt install python3-venv)."
fi

if ! cmp -s backend/requirements.txt .venv/requirements.installed; then
  echo "Installing dependencies (first run only, needs internet)..."
  .venv/bin/python -m pip install --disable-pip-version-check -q -r backend/requirements.txt \
    || fail "pip install failed. Check your internet connection and try again."
  cp backend/requirements.txt .venv/requirements.installed
fi

cd backend || exit 1
../.venv/bin/python -m gufu.launch || fail "GuFu stopped with an error (see the messages above)."
