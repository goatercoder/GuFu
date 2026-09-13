"""Assemble everything the company page needs, fetching on demand when the cache is cold."""

from __future__ import annotations

from gufu.jobs.builder import Builder
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
        try:
            await Builder(state).build_one(p.ticker)
        except Exception as exc:  # noqa: BLE001
            raise DataUnavailable(str(exc)) from exc
        p = state.profile(ticker) or p
        cached = state.repo.get_financials(p.cik) if p.cik else None
        if cached is None:
            raise DataUnavailable("financials could not be built")
    return Financials.from_dict(cached), {"ticker": p.ticker, "name": p.name, "sector": p.sector,
                                          "sub_industry": p.sub_industry, "cik": p.cik}


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
