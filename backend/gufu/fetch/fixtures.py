"""Fetcher implementations: real network vs. fixture/synthetic (offline)."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Protocol

from gufu.config import Settings
from gufu.fetch import sec, stooq, yahoo
from gufu.fetch.http import RateLimiter, make_client
from gufu.fetch.synthetic import synthetic_chart, synthetic_company_tickers, synthetic_companyfacts
from gufu.prices import PriceHistory, parse_yahoo_chart
from gufu.universe import CompanyProfile, stooq_symbol, yahoo_symbol

log = logging.getLogger("gufu.fetch")


class Fetchers(Protocol):
    fixture: bool

    async def company_tickers(self, profiles: list[CompanyProfile]) -> dict[str, int]: ...
    async def companyfacts(self, cik: int, ticker: str = "") -> dict: ...
    async def price_history(self, ticker: str) -> PriceHistory: ...
    async def quote(self, ticker: str) -> PriceHistory: ...
    async def close(self) -> None: ...


class LiveFetchers:
    fixture = False

    def __init__(self, settings: Settings):
        self.settings = settings
        self.sec_client = make_client(settings.sec_user_agent)
        self.web_client = make_client(yahoo.BROWSER_UA)
        self.sec_limiter = RateLimiter(settings.sec_rps)
        self.sec_sem = asyncio.Semaphore(settings.sec_concurrency)
        self.yahoo_sem = asyncio.Semaphore(settings.yahoo_concurrency)

    async def company_tickers(self, profiles: list[CompanyProfile]) -> dict[str, int]:
        return await sec.fetch_company_tickers(self.sec_client, self.sec_limiter)

    async def companyfacts(self, cik: int, ticker: str = "") -> dict:
        async with self.sec_sem:
            return await sec.fetch_companyfacts(self.sec_client, cik, self.sec_limiter)

    async def price_history(self, ticker: str) -> PriceHistory:
        async with self.yahoo_sem:
            try:
                return await yahoo.fetch_chart(self.web_client, yahoo_symbol(ticker), "max")
            except Exception as exc:  # noqa: BLE001
                log.warning("Yahoo failed for %s (%s); trying Stooq", ticker, exc)
                return await stooq.fetch_daily_csv(self.web_client, stooq_symbol(ticker), ticker)

    async def quote(self, ticker: str) -> PriceHistory:
        async with self.yahoo_sem:
            return await yahoo.fetch_chart(self.web_client, yahoo_symbol(ticker), "5d")

    async def close(self) -> None:
        await self.sec_client.aclose()
        await self.web_client.aclose()


class FixtureFetchers:
    """Reads backend/fixtures/*.json when present, else deterministic synthetic data."""

    fixture = True

    def __init__(self, settings: Settings):
        self.dir: Path = settings.fixture_dir
        self._profiles: dict[str, CompanyProfile] = {}
        self._cik_to_ticker: dict[int, str] = {}

    def _load(self, name: str) -> dict | None:
        p = self.dir / name
        if p.exists():
            with open(p, encoding="utf-8") as fh:
                return json.load(fh)
        return None

    async def company_tickers(self, profiles: list[CompanyProfile]) -> dict[str, int]:
        self._profiles = {p.ticker: p for p in profiles}
        data = self._load("company_tickers.json") or synthetic_company_tickers([(p.ticker, p.name) for p in profiles])
        out = {}
        for row in data.values():
            out[str(row["ticker"]).upper()] = int(row["cik_str"])
        # keep well-known real CIKs for the bundled fixtures
        for p in profiles:
            if p.cik:
                out[p.ticker.replace(".", "-")] = p.cik
        for t, cik in out.items():
            self._cik_to_ticker.setdefault(cik, t.replace("-", "."))
        return out

    async def companyfacts(self, cik: int, ticker: str = "") -> dict:
        ticker = ticker or self._cik_to_ticker.get(cik, "")
        doc = self._load(f"companyfacts_{ticker}.json") if ticker else None
        if doc is None:
            prof = self._profiles.get(ticker)
            bank = bool(prof and prof.sector == "Financials")
            doc = synthetic_companyfacts(ticker or f"CIK{cik}", cik, prof.name if prof else "", bank=bank)
        await asyncio.sleep(0)
        return doc

    async def price_history(self, ticker: str) -> PriceHistory:
        data = self._load(f"yahoo_chart_{ticker}.json") or synthetic_chart(yahoo_symbol(ticker))
        await asyncio.sleep(0)
        return parse_yahoo_chart(data, yahoo_symbol(ticker))

    async def quote(self, ticker: str) -> PriceHistory:
        return await self.price_history(ticker)

    async def close(self) -> None:
        return None


def make_fetchers(settings: Settings) -> Fetchers:
    if settings.fixture_mode:
        return FixtureFetchers(settings)
    return LiveFetchers(settings)
