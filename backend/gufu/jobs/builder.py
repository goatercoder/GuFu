"""Background data builds: SEC facts -> normalized financials, prices, metrics."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from gufu.fetch.sec import max_filed
from gufu.metrics.engine import Quote, compute_metrics
from gufu.prices import PriceHistory
from gufu.services.screener_service import rebuild_screener
from gufu.state import AppState
from gufu.store.repo import now_iso
from gufu.universe import CompanyProfile, resolve_ciks
from gufu.xbrl.models import Financials
from gufu.xbrl.normalize import normalize

log = logging.getLogger("gufu.jobs")


class JobHandle:
    def __init__(self, state: AppState, kind: str, total: int):
        self.state = state
        self.id = state.repo.create_job(kind, total)
        self.total = total
        self.done = 0
        self.failed = 0
        self.errors: dict[str, str] = {}
        self._last_flush = 0

    def tick(self, ticker: str | None = None, error: str | None = None) -> None:
        self.done += 1
        if error and ticker:
            self.failed += 1
            self.errors[ticker] = error[:300]
        if self.done - self._last_flush >= 5 or self.done >= self.total:
            self.flush()

    def flush(self, status: str = "running") -> None:
        self._last_flush = self.done
        self.state.repo.update_job(self.id, status=status, done=self.done, failed=self.failed, errors=self.errors,
                                   total=self.total)

    def finish(self, status: str = "done") -> None:
        self.state.repo.update_job(self.id, status=status, done=self.done, failed=self.failed, errors=self.errors,
                                   finished_at=now_iso(), total=self.total)


def _age_hours(iso: str | None) -> float:
    if not iso:
        return 1e9
    try:
        then = datetime.fromisoformat(iso)
    except ValueError:
        return 1e9
    if then.tzinfo is None:
        then = then.replace(tzinfo=UTC)
    return (datetime.now(UTC) - then).total_seconds() / 3600.0


def quote_from_history(ph: PriceHistory) -> Quote:
    m = ph.meta
    return Quote(price=ph.last_price, prev_close=m.get("prev_close"), high52=m.get("high52"), low52=m.get("low52"),
                 as_of=m.get("as_of"), currency=ph.currency)


class Builder:
    def __init__(self, state: AppState):
        self.s = state

    # ------------------------------------------------------------------ universe
    async def ensure_ciks(self) -> None:
        missing = [p for p in self.s.profiles if not p.cik]
        cached = {p.ticker: p for p in self.s.repo.get_companies()}
        # take CIKs already stored in sqlite
        merged: list[CompanyProfile] = []
        for p in self.s.profiles:
            c = cached.get(p.ticker)
            merged.append(CompanyProfile(p.ticker, p.name, p.sector, p.sub_industry, p.cik or (c.cik if c else None)))
        missing = [p for p in merged if not p.cik]
        if missing:
            try:
                tmap = await self.s.fetchers.company_tickers(merged)
                merged = resolve_ciks(merged, tmap)
            except Exception as exc:  # noqa: BLE001
                log.warning("could not fetch SEC ticker map: %s", exc)
        self.s.profiles = merged
        self.s.profile_by_ticker = {p.ticker: p for p in merged}
        self.s.repo.upsert_companies(merged)
        still = [p.ticker for p in merged if not p.cik]
        if still:
            log.warning("%d tickers without CIK: %s", len(still), ", ".join(still[:15]))

    # ------------------------------------------------------------------ facts
    async def fetch_and_store_facts(self, profile: CompanyProfile, force: bool = False) -> Financials | None:
        if not profile.cik:
            raise RuntimeError("no CIK for ticker")
        meta = self.s.repo.raw_facts_meta(profile.cik)
        fin_cached = self.s.repo.get_financials(profile.cik)
        if not force and meta and fin_cached and _age_hours(meta[0]) < self.s.settings.facts_max_age_days * 24:
            return Financials.from_dict(fin_cached)
        doc = await self.s.fetchers.companyfacts(profile.cik, profile.ticker)
        filed_max = max_filed(doc)
        if not force and meta and fin_cached and meta[1] == filed_max:
            # nothing new was filed; just refresh the fetch timestamp
            self.s.repo.db.execute("UPDATE raw_facts SET fetched_at=? WHERE cik=?", (now_iso(), profile.cik))
            return Financials.from_dict(fin_cached)
        fin = await asyncio.to_thread(normalize, doc)
        if self.s.settings.keep_raw_facts:
            await asyncio.to_thread(self.s.repo.put_raw_facts, profile.cik, doc, filed_max)
        else:
            self.s.repo.db.execute(
                "INSERT OR REPLACE INTO raw_facts(cik,fetched_at,filed_max,body) VALUES(?,?,?,NULL)",
                (profile.cik, now_iso(), filed_max),
            )
        self.s.repo.put_financials(
            profile.cik, fin.to_dict(), fin.latest_10k_filed.isoformat() if fin.latest_10k_filed else None,
            fin.latest_10q_filed.isoformat() if fin.latest_10q_filed else None,
        )
        return fin

    async def build_facts(self, tickers: list[str], job: JobHandle | None = None, force: bool = False) -> None:
        seen_cik: set[int] = set()
        sem = asyncio.Semaphore(self.s.settings.sec_concurrency)

        async def one(p: CompanyProfile):
            async with sem:
                try:
                    if not p.cik:
                        raise RuntimeError("no CIK")
                    if p.cik in seen_cik:
                        return
                    seen_cik.add(p.cik)
                    await self.fetch_and_store_facts(p, force=force)
                    if job:
                        job.tick(p.ticker)
                except Exception as exc:  # noqa: BLE001
                    log.warning("facts failed for %s: %s", p.ticker, exc)
                    if job:
                        job.tick(p.ticker, str(exc))

        await asyncio.gather(*(one(self.s.profile_by_ticker[t]) for t in tickers if t in self.s.profile_by_ticker))

    # ------------------------------------------------------------------ prices
    async def fetch_and_store_prices(self, ticker: str, force: bool = False) -> PriceHistory:
        cached = self.s.repo.get_prices(ticker)
        if not force and cached and _age_hours(cached[1]) < self.s.settings.prices_max_age_hours:
            return PriceHistory.from_dict(cached[0])
        ph = await self.s.fetchers.price_history(ticker)
        self.s.repo.put_prices(ticker, ph.to_dict())
        return ph

    async def build_prices(self, tickers: list[str], job: JobHandle | None = None, force: bool = False) -> None:
        sem = asyncio.Semaphore(max(1, self.s.settings.yahoo_concurrency))

        async def one(t: str):
            async with sem:
                try:
                    await self.fetch_and_store_prices(t, force=force)
                    if job:
                        job.tick(t)
                except Exception as exc:  # noqa: BLE001
                    log.warning("prices failed for %s: %s", t, exc)
                    if job:
                        job.tick(t, str(exc))

        await asyncio.gather(*(one(t) for t in tickers))

    # ------------------------------------------------------------------ metrics
    def compute_and_store_metrics(self, profile: CompanyProfile, fin: Financials, ph: PriceHistory | None) -> dict:
        quote = quote_from_history(ph) if ph else Quote(price=None)
        res = compute_metrics(fin, quote, profile.sector)
        body: dict[str, Any] = {
            "ticker": profile.ticker, "name": profile.name, "sector": profile.sector, "sub_industry": profile.sub_industry,
            "cik": profile.cik, **res, "quote": quote.to_dict(),
            "data_status": {
                "latest_10k_filed": fin.latest_10k_filed.isoformat() if fin.latest_10k_filed else None,
                "latest_10q_filed": fin.latest_10q_filed.isoformat() if fin.latest_10q_filed else None,
                "fye_month": fin.fye_month, "annual_years": len(fin.annual), "quarters": len(fin.quarterly),
                "warnings": fin.warnings,
            },
        }
        self.s.repo.put_metrics(profile.ticker, body, quote.as_of)
        return body

    async def build_metrics(self, tickers: list[str], job: JobHandle | None = None) -> None:
        for i, t in enumerate(tickers):
            if i and i % 25 == 0:
                rebuild_screener(self.s)  # let the home page / screener fill in while the build runs
                await asyncio.sleep(0)
            p = self.s.profile_by_ticker.get(t)
            try:
                if not p or not p.cik:
                    raise RuntimeError("no CIK")
                fin_d = self.s.repo.get_financials(p.cik)
                if not fin_d:
                    raise RuntimeError("no financials cached")
                pr = self.s.repo.get_prices(t)
                ph = PriceHistory.from_dict(pr[0]) if pr else None
                fin = Financials.from_dict(fin_d)
                await asyncio.to_thread(self.compute_and_store_metrics, p, fin, ph)
                if job:
                    job.tick(t)
            except Exception as exc:  # noqa: BLE001
                log.warning("metrics failed for %s: %s", t, exc)
                if job:
                    job.tick(t, str(exc))
        rebuild_screener(self.s)

    # ------------------------------------------------------------------ orchestration
    async def build_all(self, kind: str = "all", force: bool = False) -> int:
        async with self.s.build_lock:
            await self.ensure_ciks()
            tickers = [p.ticker for p in self.s.profiles]
            steps = {"facts": 1, "prices": 1, "metrics": 1} if kind == "all" else {kind: 1, "metrics": 1}
            if kind == "metrics":
                steps = {"metrics": 1}
            job = JobHandle(self.s, kind, total=len(tickers) * len(steps))
            self.s.current_job_id = job.id
            try:
                if "facts" in steps:
                    await self.build_facts(tickers, job, force=force)
                if "prices" in steps:
                    await self.build_prices(tickers, job, force=force)
                await self.build_metrics(tickers, job)
                job.finish("done")
                now = now_iso()
                if "facts" in steps:
                    self.s.repo.kv_set("last_facts_build", now)
                if "prices" in steps:
                    self.s.repo.kv_set("last_prices_build", now)
                self.s.repo.kv_set("last_metrics_build", now)
            except Exception as exc:  # noqa: BLE001
                log.exception("build failed")
                job.errors["__job__"] = str(exc)
                job.finish("failed")
            finally:
                self.s.current_job_id = None
            return job.id

    async def build_one(self, ticker: str, force: bool = False) -> dict:
        """On-demand path used by the company page when the cache is cold. Coalesces concurrent calls."""
        fut = self.s.inflight.get(ticker)
        if fut is not None:
            return await fut
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self.s.inflight[ticker] = fut
        try:
            p = self.s.profile_by_ticker.get(ticker)
            if p is None:
                raise KeyError(ticker)
            if not p.cik:
                await self.ensure_ciks()
                p = self.s.profile_by_ticker[ticker]
            fin_task = self.fetch_and_store_facts(p, force=force)
            px_task = self.fetch_and_store_prices(ticker, force=force)
            fin, ph = await asyncio.gather(fin_task, px_task, return_exceptions=True)
            if isinstance(fin, Exception) or fin is None:
                raise RuntimeError(f"SEC financials unavailable: {fin}")
            if isinstance(ph, Exception):
                log.warning("prices unavailable for %s: %s", ticker, ph)
                ph = None
            body = await asyncio.to_thread(self.compute_and_store_metrics, p, fin, ph)
            rebuild_screener(self.s)
            fut.set_result(body)
            return body
        except Exception as exc:
            fut.set_exception(exc)
            raise
        finally:
            self.s.inflight.pop(ticker, None)
