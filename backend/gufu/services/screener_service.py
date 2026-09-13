"""In-memory screener over cached metrics."""

from __future__ import annotations

import statistics
from typing import Any

from gufu.metrics.definitions import DEFAULT_SCREENER_COLUMNS, METRIC_BY_KEY, METRIC_DEFS
from gufu.state import AppState
from gufu.store.repo import now_iso

BASE_COLUMNS = ["ticker", "name", "sector", "sub_industry"]
SCREENABLE = [d.key for d in METRIC_DEFS if d.screenable]


def flatten(body: dict) -> dict[str, Any]:
    row: dict[str, Any] = {k: body.get(k) for k in BASE_COLUMNS}
    row.update({k: v for k, v in body.get("values", {}).items()})
    row["price_as_of"] = (body.get("quote") or {}).get("as_of")
    return row


def rebuild_screener(state: AppState) -> None:
    rows = [flatten(b) for b in state.repo.get_all_metrics().values()]
    rows.sort(key=lambda r: r["ticker"])
    state.screener_rows = rows
    state.screener_built_at = now_iso()


def _num(v: Any) -> float | None:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def query_screener(
    rows: list[dict], *, sector: str | None = None, sub_industry: str | None = None, search: str | None = None,
    ranges: dict[str, tuple[float | None, float | None]] | None = None, sort: str = "market_cap", order: str = "desc",
    page: int = 1, page_size: int = 50, columns: list[str] | None = None,
) -> dict:
    out = rows
    if sector:
        out = [r for r in out if r.get("sector") == sector]
    if sub_industry:
        out = [r for r in out if r.get("sub_industry") == sub_industry]
    if search:
        s = search.lower()
        out = [r for r in out if s in r["ticker"].lower() or s in (r.get("name") or "").lower()]
    for key, (lo, hi) in (ranges or {}).items():
        if lo is None and hi is None:
            continue
        out = [r for r in out if _num(r.get(key)) is not None and (lo is None or r[key] >= lo) and (hi is None or r[key] <= hi)]
    reverse = order != "asc"
    sort_key = sort if sort in METRIC_BY_KEY or sort in BASE_COLUMNS else "market_cap"

    def sk(r):
        v = r.get(sort_key)
        if sort_key in BASE_COLUMNS:
            return (0, str(v or ""))
        v = _num(v)
        return (1, 0.0) if v is None else (0, v)

    if sort_key in BASE_COLUMNS:
        out = sorted(out, key=sk, reverse=reverse)
    else:
        present = sorted([r for r in out if _num(r.get(sort_key)) is not None], key=lambda r: r[sort_key], reverse=reverse)
        absent = [r for r in out if _num(r.get(sort_key)) is None]
        out = present + absent
    total = len(out)
    page = max(1, page)
    page_size = max(1, min(500, page_size))
    start = (page - 1) * page_size
    cols = [c for c in (columns or DEFAULT_SCREENER_COLUMNS) if c in METRIC_BY_KEY]
    keep = BASE_COLUMNS + ["price", "change_pct", "price_as_of"] + cols
    page_rows = [{k: r.get(k) for k in keep} for r in out[start : start + page_size]]
    return {"total": total, "page": page, "page_size": page_size, "rows": page_rows, "columns": cols}


def facets(rows: list[dict]) -> dict:
    sectors: dict[str, int] = {}
    subs: dict[str, int] = {}
    for r in rows:
        sectors[r.get("sector") or "Unknown"] = sectors.get(r.get("sector") or "Unknown", 0) + 1
        subs[r.get("sub_industry") or "Unknown"] = subs.get(r.get("sub_industry") or "Unknown", 0) + 1
    return {
        "sectors": [{"name": k, "count": v} for k, v in sorted(sectors.items())],
        "sub_industries": [{"name": k, "count": v} for k, v in sorted(subs.items())],
        "screenable": [METRIC_BY_KEY[k].to_dict() for k in SCREENABLE],
    }


def _median(vals: list[float]) -> float | None:
    return statistics.median(vals) if vals else None


def home_summary(state: AppState, profiles_total: int) -> dict:
    rows = state.screener_rows
    with_price = [r for r in rows if _num(r.get("price")) is not None]
    mcaps = [r["market_cap"] for r in rows if _num(r.get("market_cap"))]
    pes = [r["pe"] for r in rows if _num(r.get("pe")) and 0 < r["pe"] < 200]
    yields = [r["dividend_yield"] for r in rows if _num(r.get("dividend_yield")) is not None]
    movers = sorted([r for r in with_price if _num(r.get("change_pct")) is not None], key=lambda r: r["change_pct"])

    def pick(r):
        return {"ticker": r["ticker"], "name": r["name"], "sector": r["sector"], "price": r.get("price"),
                "change_pct": r.get("change_pct"), "market_cap": r.get("market_cap"), "pe": r.get("pe"),
                "roe": r.get("roe"), "dividend_yield": r.get("dividend_yield"), "peg": r.get("peg"),
                "margin_of_safety": r.get("margin_of_safety"), "piotroski_f": r.get("piotroski_f")}

    sectors: dict[str, dict] = {}
    for r in rows:
        s = r.get("sector") or "Unknown"
        d = sectors.setdefault(s, {"sector": s, "count": 0, "market_cap": 0.0, "pes": [], "changes": []})
        d["count"] += 1
        if _num(r.get("market_cap")):
            d["market_cap"] += r["market_cap"]
        if _num(r.get("pe")) and 0 < r["pe"] < 200:
            d["pes"].append(r["pe"])
        if _num(r.get("change_pct")) is not None:
            d["changes"].append(r["change_pct"])
    sector_rows = [
        {"sector": d["sector"], "count": d["count"], "market_cap": d["market_cap"], "median_pe": _median(d["pes"]),
         "avg_change_pct": (sum(d["changes"]) / len(d["changes"])) if d["changes"] else None}
        for d in sorted(sectors.values(), key=lambda d: -d["market_cap"])
    ]
    cheapest = sorted([r for r in rows if _num(r.get("pe")) and r["pe"] > 0], key=lambda r: r["pe"])[:10]
    top_roe = sorted([r for r in rows if _num(r.get("roe")) is not None and (r.get("equity_to_assets") or 1) > 0],
                     key=lambda r: -r["roe"])[:10]
    undervalued = sorted([r for r in rows if _num(r.get("margin_of_safety")) is not None and (r.get("pe") or 0) > 0],
                         key=lambda r: -r["margin_of_safety"])[:10]
    quality = sorted([r for r in rows if _num(r.get("piotroski_f")) is not None],
                     key=lambda r: (-(r["piotroski_f"] or 0), -(r.get("roic") or 0)))[:10]
    biggest = sorted([r for r in rows if _num(r.get("market_cap"))], key=lambda r: -r["market_cap"])[:10]
    job = state.repo.latest_job()
    return {
        "as_of": state.screener_built_at,
        "fixture_mode": state.fetchers.fixture,
        "stats": {
            "companies": profiles_total, "with_data": len(rows), "with_price": len(with_price),
            "total_market_cap": sum(mcaps) if mcaps else None, "median_pe": _median(pes),
            "median_dividend_yield": _median(yields),
            "advancers": sum(1 for r in movers if r["change_pct"] > 0), "decliners": sum(1 for r in movers if r["change_pct"] < 0),
        },
        "sectors": sector_rows,
        "movers": {"gainers": [pick(r) for r in movers[::-1][:8]], "losers": [pick(r) for r in movers[:8]]},
        "cheapest_pe": [pick(r) for r in cheapest],
        "highest_roe": [pick(r) for r in top_roe],
        "undervalued_dcf": [pick(r) for r in undervalued],
        "quality": [pick(r) for r in quality],
        "largest": [pick(r) for r in biggest],
        "job": job,
    }


# --------------------------------------------------------------------------------------------
# GuruFocus-style 1-10 rank badges and peer lists, computed from the cached universe
# --------------------------------------------------------------------------------------------

RANK_DEFS: dict[str, list[tuple[str, bool]]] = {
    # group: [(metric, higher_is_better)]
    "financial_strength": [("altman_z", True), ("interest_coverage", True), ("debt_to_equity", False), ("cash_to_debt", True),
                           ("equity_to_assets", True), ("current_ratio", True)],
    "profitability": [("roe", True), ("roic", True), ("operating_margin", True), ("net_margin", True), ("gross_margin", True),
                      ("piotroski_f", True)],
    "growth": [("revenue_growth_5y", True), ("eps_growth_5y", True), ("revenue_growth_10y", True), ("fcf_growth_5y", True),
               ("revenue_growth_ttm", True)],
    "valuation": [("pe", False), ("ev_ebitda", False), ("pb", False), ("ps", False), ("fcf_yield", True), ("peg", False)],
}


def _percentile(sorted_vals: list[float], v: float) -> float:
    if not sorted_vals:
        return 0.5
    lo, hi = 0, len(sorted_vals)
    while lo < hi:
        mid = (lo + hi) // 2
        if sorted_vals[mid] < v:
            lo = mid + 1
        else:
            hi = mid
    return lo / len(sorted_vals)


def compute_ranks(rows: list[dict], ticker: str, values: dict[str, float | None] | None = None) -> dict:
    """1 (worst) .. 10 (best) per group = average percentile of the group's metrics across the S&P 500."""
    me = values or next((r for r in rows if r["ticker"] == ticker), None)
    if me is None:
        return {}
    out: dict[str, dict] = {}
    for group, metrics in RANK_DEFS.items():
        pcts: list[float] = []
        detail: list[dict] = []
        for key, higher in metrics:
            v = _num(me.get(key))
            if v is None:
                continue
            pool = sorted(x for x in (_num(r.get(key)) for r in rows) if x is not None)
            p = _percentile(pool, v)
            if not higher:
                p = 1.0 - p
            pcts.append(p)
            detail.append({"metric": key, "value": v, "percentile": round(p * 100)})
        if not pcts:
            out[group] = {"rank": None, "percentile": None, "detail": []}
            continue
        avg = sum(pcts) / len(pcts)
        out[group] = {"rank": max(1, min(10, int(avg * 10) + 1)), "percentile": round(avg * 100), "detail": detail}
    return out


def peers(rows: list[dict], ticker: str, sector: str, sub_industry: str, limit: int = 8) -> list[dict]:
    same_sub = [r for r in rows if r.get("sub_industry") == sub_industry and r["ticker"] != ticker]
    pool = same_sub if len(same_sub) >= 3 else [r for r in rows if r.get("sector") == sector and r["ticker"] != ticker]
    pool = sorted(pool, key=lambda r: -(_num(r.get("market_cap")) or 0))[:limit]
    keys = ["ticker", "name", "sub_industry", "price", "change_pct", "market_cap", "pe", "peg", "pb", "ev_ebitda", "dividend_yield",
            "roe", "roic", "net_margin", "revenue_growth_5y", "piotroski_f"]
    return [{k: r.get(k) for k in keys} for r in pool]
