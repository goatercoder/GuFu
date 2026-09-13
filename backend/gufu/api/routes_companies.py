from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from gufu.api.deps import get_state
from gufu.metrics.definitions import METRIC_DEFS
from gufu.prices import downsample, slice_range
from gufu.services.company_service import (
    DataUnavailable,
    UnknownTicker,
    company_bundle,
    load_financials,
    load_prices,
)
from gufu.services.quote_service import get_quote
from gufu.state import AppState
from gufu.universe import search_companies
from gufu.xbrl.tags import CHART_FIELDS, field_kind, field_label, field_unit

router = APIRouter(prefix="/api", tags=["companies"])


@router.get("/companies")
def list_companies(q: str | None = Query(None), limit: int = Query(20, ge=1, le=600), state: AppState = Depends(get_state)):
    have = {r["ticker"] for r in state.screener_rows}
    if q is None:
        profiles = state.profiles
    else:
        profiles = search_companies(state.profiles, q, limit=limit)
    return [
        {"ticker": p.ticker, "name": p.name, "sector": p.sector, "sub_industry": p.sub_industry, "has_data": p.ticker in have}
        for p in profiles
    ]


@router.get("/metrics/definitions")
def metric_definitions():
    return [d.to_dict() for d in METRIC_DEFS]


@router.get("/company/{ticker}")
async def company(ticker: str, state: AppState = Depends(get_state)):
    try:
        return await company_bundle(state, ticker)
    except UnknownTicker:
        raise HTTPException(404, "Unknown ticker (only S&P 500 constituents are supported)") from None
    except DataUnavailable as exc:
        raise HTTPException(503, f"Financial data not available yet: {exc}") from None


@router.get("/company/{ticker}/quote")
async def quote(ticker: str, state: AppState = Depends(get_state)):
    p = state.profile(ticker)
    if p is None:
        raise HTTPException(404, "Unknown ticker")
    return (await get_quote(state, p.ticker)).to_dict()


@router.get("/company/{ticker}/financials")
async def financials(ticker: str, freq: str = Query("annual", pattern="^(annual|quarterly)$"),
                     state: AppState = Depends(get_state)):
    try:
        fin, profile = await load_financials(state, ticker)
    except UnknownTicker:
        raise HTTPException(404, "Unknown ticker") from None
    except DataUnavailable as exc:
        raise HTTPException(503, f"Financial data not available yet: {exc}") from None
    rows = fin.annual if freq == "annual" else fin.quarterly
    fields = [{"key": k, "label": field_label(k), "kind": field_kind(k), "unit": field_unit(k)} for k in CHART_FIELDS]
    return {
        "ticker": profile["ticker"], "freq": freq, "fye_month": fin.fye_month, "fields": fields,
        "periods": [r.to_dict() for r in rows], "ttm": fin.ttm.to_dict() if fin.ttm else None,
        "warnings": fin.warnings, "source": "SEC EDGAR XBRL companyfacts (10-K / 10-Q)",
        "coverage_note": "Structured XBRL data begins with fiscal years ending 2009 or later; earlier years are not "
                         "available from SEC filings in machine-readable form.",
    }


@router.get("/company/{ticker}/prices")
async def prices(ticker: str, range: str = Query("1y", pattern="^(1m|3m|6m|ytd|1y|2y|5y|10y|max)$"),
                 state: AppState = Depends(get_state)):
    try:
        ph = await load_prices(state, ticker)
    except UnknownTicker:
        raise HTTPException(404, "Unknown ticker") from None
    if ph is None:
        raise HTTPException(503, "Price history not available")
    dates, closes, vols = slice_range(ph, range, today=date.today())
    dates, closes, vols, ds = downsample(dates, closes, vols)
    return {
        "ticker": ticker.upper(), "symbol": ph.symbol, "currency": ph.currency, "range": range, "downsampled": ds,
        "points": [{"d": d, "c": c, "v": v} for d, c, v in zip(dates, closes, vols, strict=True)],
        "meta": ph.meta, "first_date": ph.dates[0] if ph.dates else None, "source": "Yahoo Finance (daily close)",
    }
