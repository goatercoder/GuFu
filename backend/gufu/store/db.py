"""SQLite persistence. One connection per process, single writer lock, WAL mode."""

from __future__ import annotations

import asyncio
import sqlite3
import threading
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
  ticker TEXT PRIMARY KEY, cik INTEGER, name TEXT, sector TEXT, sub_industry TEXT
);
CREATE TABLE IF NOT EXISTS raw_facts (
  cik INTEGER PRIMARY KEY, fetched_at TEXT, filed_max TEXT, body BLOB
);
CREATE TABLE IF NOT EXISTS financials (
  cik INTEGER PRIMARY KEY, computed_at TEXT, latest_10k_filed TEXT, latest_10q_filed TEXT, body TEXT
);
CREATE TABLE IF NOT EXISTS prices (
  ticker TEXT PRIMARY KEY, fetched_at TEXT, currency TEXT, body TEXT
);
CREATE TABLE IF NOT EXISTS metrics (
  ticker TEXT PRIMARY KEY, computed_at TEXT, price_as_of TEXT, body TEXT
);
CREATE TABLE IF NOT EXISTS job_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, status TEXT, started_at TEXT, finished_at TEXT,
  total INTEGER DEFAULT 0, done INTEGER DEFAULT 0, failed INTEGER DEFAULT 0, errors TEXT DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS legacy_docs (
  cik INTEGER, accn TEXT, doc TEXT, fetched_at TEXT, body BLOB, PRIMARY KEY (cik, accn, doc)
);
CREATE TABLE IF NOT EXISTS legacy_financials (
  cik INTEGER PRIMARY KEY, computed_at TEXT, body TEXT
);
CREATE TABLE IF NOT EXISTS kv (
  key TEXT PRIMARY KEY, value TEXT
);
"""


class Database:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._alock = asyncio.Lock()
        with self._lock:
            if str(self.path) != ":memory:":
                self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.executescript(SCHEMA)

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn

    @property
    def lock(self) -> threading.RLock:
        return self._lock

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)

    def fetchone(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def fetchall(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
