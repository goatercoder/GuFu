"""Process-wide application state (settings, DB, fetchers, in-memory indexes)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from gufu.config import Settings
from gufu.fetch.fixtures import Fetchers
from gufu.store.db import Database
from gufu.store.repo import Repo
from gufu.universe import CompanyProfile


@dataclass
class AppState:
    settings: Settings
    db: Database
    repo: Repo
    fetchers: Fetchers
    profiles: list[CompanyProfile]
    profile_by_ticker: dict[str, CompanyProfile] = field(default_factory=dict)
    screener_rows: list[dict[str, Any]] = field(default_factory=list)
    screener_built_at: str | None = None
    quote_cache: dict[str, tuple[float, Any]] = field(default_factory=dict)
    build_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    inflight: dict[str, asyncio.Future] = field(default_factory=dict)
    background_tasks: set[asyncio.Task] = field(default_factory=set)
    current_job_id: int | None = None
    # Set once a SEC User-Agent is available; the scheduler waits on it before building.
    setup_done: asyncio.Event = field(default_factory=asyncio.Event)

    @property
    def setup_required(self) -> bool:
        return not self.fetchers.fixture and not self.settings.sec_user_agent.strip()

    def profile(self, ticker: str) -> CompanyProfile | None:
        return self.profile_by_ticker.get(ticker.upper().replace("-", "."))
