"""SEC EDGAR: ticker map + XBRL companyfacts."""

from __future__ import annotations

import httpx

from gufu.fetch.http import RateLimiter, get_with_retry

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"


async def fetch_company_tickers(client: httpx.AsyncClient, limiter: RateLimiter | None = None) -> dict[str, int]:
    resp = await get_with_retry(client, TICKERS_URL, limiter=limiter, headers={"Host": "www.sec.gov"})
    data = resp.json()
    out: dict[str, int] = {}
    rows = data.values() if isinstance(data, dict) else data
    for row in rows:
        t = str(row.get("ticker", "")).upper()
        if t:
            out[t] = int(row["cik_str"])
    return out


async def fetch_companyfacts(client: httpx.AsyncClient, cik: int, limiter: RateLimiter | None = None) -> dict:
    url = COMPANYFACTS_URL.format(cik=cik)
    resp = await get_with_retry(client, url, limiter=limiter, headers={"Host": "data.sec.gov"})
    return resp.json()


def max_filed(cf: dict) -> str | None:
    best: str | None = None
    for tax in cf.get("facts", {}).values():
        for node in tax.values():
            for series in node.get("units", {}).values():
                for f in series:
                    fd = f.get("filed")
                    if fd and (best is None or fd > best):
                        best = fd
    return best
