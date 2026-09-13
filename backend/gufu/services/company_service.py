"""Assemble everything the company page needs, fetching on demand when the cache is cold."""

from __future__ import annotations

import asyncio

from gufu.fetch.fixtures import SetupRequiredFetchers
from gufu.jobs.builder import Builder
from gufu.legacy.merge import LegacyData, legacy_rows, period_source
from gufu.legacy.pipeline import coverage
from gufu.metrics.engine import compute_metrics, grouped_metrics
from gufu.prices import PriceHistory
from gufu.services.quote_service import get_quote
from gufu.state import AppState
from gufu.xbrl.models import Financials


class UnknownTicker(KeyError):
    pass


class DataUnavailable(RuntimeError):
    pass


async def load_financials(state: AppState, ticker: str) -> tuple[Financials, dict]:
    p = state.profile(ticker)
    if p is None:
        raise UnknownTicker(ticker)
    cached = state.repo.get_financials(p.cik) if p.cik else None
    if cached is None:
        if state.setup_required:
            raise DataUnavailable(SetupRequiredFetchers.MESSAGE)
        try:
            await Builder(state).build_one(p.ticker)
        except Exception as exc:  # noqa: BLE001
            raise DataUnavailable(str(exc)) from exc
        p = state.profile(ticker) or p
        cached = state.repo.get_financials(p.cik) if p.cik else None
        if cached is None:
            raise DataUnavailable("financials could not be built")
    fin = Financials.from_dict(cached)
    attach_legacy(state, fin, p.cik)
    return fin, {"ticker": p.ticker, "name": p.name, "sector": p.sector, "sub_industry": p.sub_industry, "cik": p.cik}


def attach_legacy(state: AppState, fin: Financials, cik: int | None) -> None:
    """Merge cached pre-XBRL rows (if any) into fin.annual; idempotent."""
    if not cik or fin.legacy is not None:
        return
    d = state.repo.get_legacy(cik)
    if not d:
        return
    data = LegacyData.from_dict(d)
    xbrl_fys = {r.fiscal_year for r in fin.xbrl_annual}
    rows = legacy_rows(data, fin.fye_month, xbrl_fys)
    fin.annual = sorted(fin.xbrl_annual + rows, key=lambda r: r.end)
    fin.legacy = data


async def ensure_legacy(state: AppState, ticker: str, fin: Financials, cik: int, *, timeout: float | None = None,
                        force: bool = False) -> str:
    """Make sure legacy history exists for this company. Returns 'ready' | 'building' | 'disabled' | 'failed:<msg>'."""
    if not state.settings.legacy_enabled:
        return "disabled"
    if state.setup_required:
        return "failed:" + SetupRequiredFetchers.MESSAGE
    if not force and state.repo.get_legacy(cik) is not None:
        return "ready"
    key = f"legacy:{cik}"
    task = state.inflight.get(key)
    if task is None:
        loop = asyncio.get_running_loop()
        task = loop.create_task(Builder(state).fetch_and_store_legacy(state.profile(ticker), fin, force=force))
        state.inflight[key] = task
        task.add_done_callback(lambda _t: state.inflight.pop(key, None))
        state.background_tasks.add(task)
        task.add_done_callback(state.background_tasks.discard)
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=timeout or state.settings.legacy_on_demand_timeout)
    except TimeoutError:
        return "building"
    except Exception as exc:  # noqa: BLE001
        return f"failed:{exc}"
    return "ready"


def legacy_summary(fin: Financials) -> dict:
    data: LegacyData | None = fin.legacy
    xbrl = fin.xbrl_annual
    first = xbrl[0].fiscal_year if xbrl else None
    last = xbrl[-1].fiscal_year if xbrl else None
    years = sorted(data.years) if data else []
    return {
        "coverage": coverage(first, last, [y for y in years if first is None or y < first]),
        "legacy_warnings": data.warnings if data else [],
        "legacy_filings": data.filings if data else [],
    }


def legacy_period_source(fin: Financials, fy: int) -> dict | None:
    return period_source(fin.legacy, fy) if fin.legacy else None


async def load_prices(state: AppState, ticker: str) -> PriceHistory | None:
    p = state.profile(ticker)
    if p is None:
        raise UnknownTicker(ticker)
    cached = state.repo.get_prices(p.ticker)
    if cached is None:
        try:
            return await Builder(state).fetch_and_store_prices(p.ticker)
        except Exception:  # noqa: BLE001
            return None
    return PriceHistory.from_dict(cached[0])


async def company_bundle(state: AppState, ticker: str) -> dict:
    fin, profile = await load_financials(state, ticker)
    quote = await get_quote(state, profile["ticker"])
    res = compute_metrics(fin, quote, profile["sector"])
    ttm = fin.ttm
    return {
        "profile": profile,
        "quote": quote.to_dict(),
        "metrics": res["values"],
        "groups": grouped_metrics(res["values"]),
        "scores": res["scores"],
        "dcf": res["dcf"],
        "inputs": res["inputs"],
        "ttm": ttm.to_dict() if ttm else None,
        "data_status": {
            "latest_10k_filed": fin.latest_10k_filed.isoformat() if fin.latest_10k_filed else None,
            "latest_10q_filed": fin.latest_10q_filed.isoformat() if fin.latest_10q_filed else None,
            "fye_month": fin.fye_month, "annual_years": len(fin.annual), "quarters": len(fin.quarterly),
            "first_fiscal_year": fin.annual[0].fiscal_year if fin.annual else None,
            "last_fiscal_year": fin.annual[-1].fiscal_year if fin.annual else None,
            "warnings": fin.warnings, "entity_name": fin.entity_name, "fixture_mode": state.fetchers.fixture,
        },
    }
