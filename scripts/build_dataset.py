#!/usr/bin/env python3
"""Build the complete S&P 500 cache headlessly (used by the nightly GitHub Actions job).

Usage: GUFU_SEC_USER_AGENT="GuFu bot you@example.com" python scripts/build_dataset.py --db build/gufu.sqlite [--slim build/gufu-data.sqlite]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from gufu.config import Settings  # noqa: E402
from gufu.dataset import compress, slim_copy  # noqa: E402
from gufu.jobs.builder import Builder  # noqa: E402
from gufu.main import build_state  # noqa: E402


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="build/gufu.sqlite")
    ap.add_argument("--slim", default="build/gufu-data.sqlite")
    ap.add_argument("--kind", default="all", choices=["all", "facts", "legacy", "prices", "metrics"])
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--fixture", action="store_true", help="offline synthetic data (for testing the pipeline)")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = Settings(db_path=Path(a.db).resolve(), fixture_mode=a.fixture or os.environ.get("GUFU_FIXTURE_MODE") == "1",
                        auto_build_on_start=False, dataset_url="", keep_raw_facts=False)
    if not settings.fixture_mode and not settings.sec_user_agent.strip():
        print("GUFU_SEC_USER_AGENT is required (SEC EDGAR needs a contact User-Agent)", file=sys.stderr)
        return 2
    state = build_state(settings)
    b = Builder(state)
    t0 = time.time()
    await b.build_all(a.kind, force=a.force)
    job = state.repo.latest_job()
    print(f"build {job['status']}: {job['done']}/{job['total']} steps, {job['failed']} failed, {time.time() - t0:.0f}s")
    for t, err in list(job["errors"].items())[:25]:
        print(f"  {t}: {err}")
    await state.fetchers.close()
    state.db.close()
    if a.slim:
        size = slim_copy(Path(a.db), Path(a.slim))
        gz = compress(Path(a.slim), Path(a.slim + ".gz"))
        print(f"slim dataset: {size / 1e6:.1f} MB, gzipped {gz / 1e6:.1f} MB -> {a.slim}.gz")
    return 0 if job["status"] == "done" else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
