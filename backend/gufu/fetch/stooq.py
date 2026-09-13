"""Stooq daily CSV as a fallback price source (no key, generous but capped)."""

from __future__ import annotations

import httpx

from gufu.fetch.http import get_with_retry
from gufu.prices import PriceHistory, parse_stooq_csv


async def fetch_daily_csv(client: httpx.AsyncClient, stooq_sym: str, display_symbol: str) -> PriceHistory:
    url = "https://stooq.com/q/d/l/"
    resp = await get_with_retry(client, url, retries=1, params={"s": stooq_sym, "i": "d"},
                                headers={"User-Agent": "Mozilla/5.0"})
    return parse_stooq_csv(resp.text, display_symbol)
