"""One-click entry point: pick a port, start the server, open the browser once it answers.

Run from the backend directory:  python -m gufu.launch     (the start.* scripts do this for you)
"""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
REPO = BACKEND.parent


def _gufu_at(port: int) -> bool:
    """True when a GuFu server is already answering on this port."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1) as r:
            return "companies" in json.load(r)
    except Exception:  # noqa: BLE001
        return False


def _free_port(start: int, tries: int = 20) -> int:
    for p in range(start, start + tries):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    raise SystemExit(f"No free port between {start} and {start + tries - 1}.")


def _open_when_ready(url: str, port: int, open_browser: bool) -> None:
    for _ in range(240):  # up to 2 minutes; first start on an old laptop can be slow
        if _gufu_at(port):
            break
        time.sleep(0.5)
    print(f"\n  GuFu is running at {url}\n  Keep this window open while you use it. Close it (or press Ctrl+C) to stop.\n",
          flush=True)
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass


def _warn_stale_dist() -> None:
    dist = REPO / "frontend" / "dist" / "index.html"
    src = REPO / "frontend" / "src"
    if not dist.exists():
        print("WARNING: frontend/dist is missing, so only the API (/docs) will work. Developers: run `make build`.")
        return
    if src.exists():
        newest = max((p.stat().st_mtime for p in src.rglob("*") if p.is_file()), default=0.0)
        if newest > dist.stat().st_mtime + 60:
            print("NOTE: frontend/src is newer than frontend/dist. Developers: run `make build` to refresh the UI.")


def main() -> int:
    os.chdir(BACKEND)
    want = int(os.environ.get("GUFU_PORT", "8000"))
    open_browser = os.environ.get("GUFU_NO_BROWSER", "") not in ("1", "true", "yes")
    if _gufu_at(want):
        url = f"http://127.0.0.1:{want}"
        print(f"GuFu is already running at {url}; opening it.")
        if open_browser:
            webbrowser.open(url)
        return 0
    port = _free_port(want)
    if port != want:
        print(f"Port {want} is busy; using {port} instead.")
    _warn_stale_dist()
    url = f"http://127.0.0.1:{port}"
    threading.Thread(target=_open_when_ready, args=(url, port, open_browser), daemon=True).start()
    try:
        import uvicorn
    except ImportError:
        print("Dependencies are not installed. Run start.sh / start.bat / start.command, or `pip install -r backend/requirements.txt`.")
        return 1
    try:
        uvicorn.run("gufu.main:app", host="127.0.0.1", port=port, log_level="info")
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
