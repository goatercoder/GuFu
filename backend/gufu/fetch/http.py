"""Shared async HTTP client, token-bucket rate limiter and retry helper."""

from __future__ import annotations

import asyncio
import logging
import time

import httpx

log = logging.getLogger("gufu.fetch")


class RateLimiter:
    """Simple token bucket: at most `rate` acquisitions per second, burst of `burst`."""

    def __init__(self, rate: float, burst: int | None = None):
        self.rate = rate
        self.capacity = burst or max(1, int(rate))
        self.tokens = float(self.capacity)
        self.updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
                self.updated = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
                await asyncio.sleep((1 - self.tokens) / self.rate)


def make_client(user_agent: str, timeout: float = 30.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(timeout, connect=15.0),
        headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate", "Accept": "*/*"},
        follow_redirects=True,
    )


class FetchError(Exception):
    pass


async def get_with_retry(
    client: httpx.AsyncClient, url: str, *, limiter: RateLimiter | None = None, retries: int = 3, backoff: float = 1.5,
    headers: dict | None = None, params: dict | None = None,
) -> httpx.Response:
    last: Exception | None = None
    for attempt in range(retries + 1):
        if limiter:
            await limiter.acquire()
        try:
            resp = await client.get(url, headers=headers, params=params)
            if resp.status_code in (429, 500, 502, 503, 504):
                raise FetchError(f"HTTP {resp.status_code} for {url}")
            if resp.status_code >= 400:
                raise FetchError(f"HTTP {resp.status_code} for {url}: {resp.text[:200]}")
            return resp
        except (httpx.HTTPError, FetchError) as exc:
            last = exc
            if attempt < retries:
                delay = backoff * (2**attempt)
                log.debug("retry %s in %.1fs: %s", url, delay, exc)
                await asyncio.sleep(delay)
    raise FetchError(str(last))
