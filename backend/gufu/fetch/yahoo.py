"""Yahoo Finance (unofficial) chart endpoint: daily history + live quote."""

from __future__ import annotations

import httpx

from gufu.fetch.http import FetchError, get_with_retry
from gufu.prices import PriceHistory, parse_yahoo_chart

HOSTS = ("query1.finance.yahoo.com", "query2.finance.yahoo.com")
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


async def fetch_chart(client: httpx.AsyncClient, symbol: str, rng: str = "max", interval: str = "1d") -> PriceHistory:
    last: Exception | None = None
    for host in HOSTS:
        url = f"https://{host}/v8/finance/chart/{symbol}"
        try:
            resp = await get_with_retry(
                client, url, retries=2, headers={"User-Agent": BROWSER_UA, "Accept": "application/json"},
                params={"range": rng, "interval": interval, "events": "div,split", "includeAdjustedClose": "true"},
            )
            return parse_yahoo_chart(resp.json(), symbol)
        except (FetchError, ValueError, httpx.HTTPError) as exc:
            last = exc
    raise FetchError(f"Yahoo chart failed for {symbol}: {last}")
