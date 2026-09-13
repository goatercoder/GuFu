"""One-time setup: build, validate and persist the SEC User-Agent, then swap in live fetchers."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from gufu.fetch.fixtures import make_fetchers
from gufu.state import AppState

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
USER_AGENT_PREFIX = "GuFu/0.1"


def build_user_agent(name: str, email: str) -> str:
    name = " ".join(name.split())
    email = email.strip()
    if not (2 <= len(name) <= 80) or any(ch in name for ch in '"\n\r;()'):
        raise ValueError("Name must be 2-80 characters without quotes, parentheses or semicolons")
    if not EMAIL_RE.match(email) or len(email) > 120:
        raise ValueError("Please enter a valid email address")
    return f"{USER_AGENT_PREFIX} ({name}; {email})"


def write_env_value(path: Path, key: str, value: str) -> None:
    """Set KEY="value" in a dotenv file, replacing an existing (or commented-out) line; atomic on POSIX."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    new_line = f'{key}="{value}"'
    out: list[str] = []
    done = False
    for ln in lines:
        head = ln.split("=", 1)[0].strip()
        if head in (key, f"#{key}", f"# {key}"):
            if not done:
                out.append(new_line)
                done = True
            continue
        out.append(ln)
    if not done:
        out.append(new_line)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".env.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write("\n".join(out) + "\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


async def apply_user_agent(state: AppState, ua: str) -> None:
    """Switch the running app to live fetchers using `ua`, remember it, and release the scheduler."""
    state.settings.sec_user_agent = ua
    old = state.fetchers
    state.fetchers = make_fetchers(state.settings)
    await old.close()
    state.repo.kv_set("sec_user_agent", ua)
    state.quote_cache.clear()
    state.setup_done.set()
