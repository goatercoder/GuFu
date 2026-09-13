"""Prebuilt dataset support: slim export of the cache and download-at-startup.

A nightly GitHub Actions job builds the whole S&P 500 cache and publishes a slim, gzipped SQLite file.
Any GuFu instance (laptop launcher, Docker, Render) downloads it on first start instead of spending
30-60 minutes talking to SEC EDGAR, so every page is instant from the first click.
"""

from __future__ import annotations

import gzip
import logging
import shutil
import sqlite3
import tempfile
import urllib.request
from pathlib import Path

log = logging.getLogger("gufu.dataset")
SLIM_TABLES = ("companies", "financials", "legacy_financials", "prices", "metrics", "kv")


def slim_copy(src: Path, dest: Path) -> int:
    """Copy only the tables needed to serve pages (no raw SEC documents). Returns size in bytes."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    con = sqlite3.connect(str(src))
    try:
        con.execute("ATTACH DATABASE ? AS slim", (str(dest),))
        for t in SLIM_TABLES:
            row = con.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone()
            if not row:
                continue
            con.execute(row[0].replace(f"CREATE TABLE IF NOT EXISTS {t}", f"CREATE TABLE slim.{t}").replace(f"CREATE TABLE {t}", f"CREATE TABLE slim.{t}"))
            con.execute(f"INSERT INTO slim.{t} SELECT * FROM main.{t}")
        con.commit()
        con.execute("DETACH DATABASE slim")
    finally:
        con.close()
    con2 = sqlite3.connect(str(dest))
    con2.execute("VACUUM")
    con2.close()
    return dest.stat().st_size


def compress(src: Path, dest: Path) -> int:
    with open(src, "rb") as fi, gzip.open(dest, "wb", compresslevel=6) as fo:
        shutil.copyfileobj(fi, fo, 1 << 20)
    return dest.stat().st_size


def db_has_data(path: Path, min_metrics: int = 100) -> bool:
    if not path.exists():
        return False
    try:
        con = sqlite3.connect(str(path))
        try:
            n = con.execute("SELECT COUNT(*) FROM metrics").fetchone()[0]
        finally:
            con.close()
        return n >= min_metrics
    except sqlite3.Error:
        return False


def download_dataset(url: str, dest: Path, timeout: float = 120.0) -> bool:
    """Fetch the gzipped prebuilt cache into `dest` (atomic replace). False on any failure."""
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "GuFu dataset fetch"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            with tempfile.NamedTemporaryFile(dir=dest.parent, suffix=".gz", delete=False) as tmp:
                shutil.copyfileobj(resp, tmp, 1 << 20)
                gz_path = Path(tmp.name)
        raw = dest.with_suffix(".download")
        with gzip.open(gz_path, "rb") as fi, open(raw, "wb") as fo:
            shutil.copyfileobj(fi, fo, 1 << 20)
        gz_path.unlink(missing_ok=True)
        if not db_has_data(raw):
            raw.unlink(missing_ok=True)
            log.warning("downloaded dataset from %s has no data; ignoring", url)
            return False
        for suffix in ("", "-wal", "-shm"):
            p = Path(str(dest) + suffix)
            if p.exists():
                p.unlink()
        raw.replace(dest)
        log.info("prebuilt dataset installed from %s (%.0f MB)", url, dest.stat().st_size / 1e6)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("prebuilt dataset download failed (%s); will build locally instead", exc)
        return False
