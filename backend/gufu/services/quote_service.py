"""Live quote with a short TTL, falling back to the last cached close."""

from __future__ import annotations

import logging
import time

from gufu.jobs.builder import quote_from_history
from gufu.metrics.engine import Quote
from gufu.prices import PriceHistory
from gufu.state import AppState

log = logging.getLogger("gufu.quote")


async def get_quote(state: AppState, ticker: str) -> Quote:
    ttl = state.settings.quote_ttl_seconds
    hit = state.quote_cache.get(ticker)
    now = time.monotonic()
    if hit and now - hit[0] < ttl:
        return hit[1]
    try:
        ph = await state.fetchers.quote(ticker)
        q = quote_from_history(ph)
        # a 5-day window has no 52-week range; borrow it from the cached full history
        if q.high52 is None or q.low52 is None:
            cached = state.repo.get_prices(ticker)
            if cached:
                full = PriceHistory.from_dict(cached[0])
                q.high52 = q.high52 or full.meta.get("high52")
                q.low52 = q.low52 or full.meta.get("low52")
    except Exception as exc:  # noqa: BLE001
        log.warning("live quote failed for %s: %s", ticker, exc)
        cached = state.repo.get_prices(ticker)
        if not cached:
            return Quote(price=None, stale=True)
        q = quote_from_history(PriceHistory.from_dict(cached[0]))
        q.stale = True
    state.quote_cache[ticker] = (now, q)
    return q
