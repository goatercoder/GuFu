from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from gufu.api.deps import get_state
from gufu.metrics.definitions import METRIC_DEFS
from gufu.prices import close_on_or_before, downsample, slice_range
from gufu.services.company_service import (
    DataUnavailable,
    UnknownTicker,
    attach_legacy,
    company_bundle,
    ensure_legacy,
    legacy_period_source,
    legacy_summary,
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
    legacy_status = "ready" if fin.legacy is not None else "none"
    if freq == "annual" and fin.legacy is None and profile["cik"]:
        legacy_status = await ensure_legacy(state, profile["ticker"], fin, profile["cik"])
        if legacy_status == "ready":
            attach_legacy(state, fin, profile["cik"])
    rows = fin.annual if freq == "annual" else fin.quarterly
    fields = [{"key": k, "label": field_label(k), "kind": field_kind(k), "unit": field_unit(k)} for k in CHART_FIELDS]
    ph = await load_prices(state, profile["ticker"]) if profile["cik"] else None
    periods = []
    for r in rows:
        d = r.to_dict()
        d["legacy"] = "legacy" in r.derived
        d["source"] = legacy_period_source(fin, r.fiscal_year) if d["legacy"] else None
        d["px"] = close_on_or_before(ph, r.end.isoformat()) if ph else None
        periods.append(d)
    ttm_d = fin.ttm.to_dict() if fin.ttm else None
    if ttm_d and ph:
        ttm_d["px"] = ph.last_price
    return {
        "ticker": profile["ticker"], "freq": freq, "fye_month": fin.fye_month, "fields": fields,
        "periods": periods, "ttm": ttm_d,
        "warnings": fin.warnings, "legacy_status": legacy_status, **legacy_summary(fin),
        "source": "SEC EDGAR: XBRL companyfacts (10-K / 10-Q, 2009+) and Selected Financial Data / statements parsed from "
                  "older 10-K filings",
        "coverage_note": "Fiscal years ending 2009 or later come from structured XBRL data. Earlier years are parsed from "
                         "the company's older 10-K filings (five-year Selected Financial Data tables and the primary "
                         "statements); each such value links to its filing and may need checking.",
    }


@router.post("/company/{ticker}/legacy/refresh")
async def refresh_legacy(ticker: str, state: AppState = Depends(get_state)):
    """Re-fetch and re-parse the older 10-K filings for one company (e.g. after a parser fix)."""
    try:
        fin, profile = await load_financials(state, ticker)
    except UnknownTicker:
        raise HTTPException(404, "Unknown ticker") from None
    except DataUnavailable as exc:
        raise HTTPException(503, str(exc)) from None
    if not profile["cik"]:
        raise HTTPException(503, "No CIK for this ticker")
    fin.legacy = None
    fin.annual = fin.xbrl_annual
    status = await ensure_legacy(state, profile["ticker"], fin, profile["cik"], force=True)
    if status == "ready":
        attach_legacy(state, fin, profile["cik"])
    return {"status": status, "legacy_years": sorted(fin.legacy.years) if fin.legacy else [],
            "warnings": fin.legacy.warnings if fin.legacy else []}


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
