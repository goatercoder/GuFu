from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from gufu.api.deps import get_state
from gufu.metrics.definitions import METRIC_BY_KEY
from gufu.services.screener_service import SCREENABLE, facets, query_screener
from gufu.state import AppState

router = APIRouter(prefix="/api", tags=["screener"])


def _parse_ranges(params) -> dict[str, tuple[float | None, float | None]]:
    ranges: dict[str, tuple[float | None, float | None]] = {}
    for raw_key, raw_val in params.multi_items():
        if raw_key.endswith("_min") or raw_key.endswith("_max"):
            key, kind = raw_key[:-4], raw_key[-3:]
            if key not in METRIC_BY_KEY or not METRIC_BY_KEY[key].screenable:
                continue
            try:
                val = float(raw_val)
            except (TypeError, ValueError):
                continue
            d = METRIC_BY_KEY[key]
            if d.fmt == "pct":
                val = val / 100.0  # UI sends percentages
            lo, hi = ranges.get(key, (None, None))
            ranges[key] = (val, hi) if kind == "min" else (lo, val)
    return ranges


@router.get("/screener")
def screener(
    request: Request, sector: str | None = None, sub_industry: str | None = None, q: str | None = None,
    sort: str = "market_cap", order: str = Query("desc", pattern="^(asc|desc)$"), page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500), columns: str | None = None, state: AppState = Depends(get_state),
):
    cols = [c for c in (columns.split(",") if columns else []) if c] or None
    res = query_screener(
        state.screener_rows, sector=sector, sub_industry=sub_industry, search=q, ranges=_parse_ranges(request.query_params),
        sort=sort, order=order, page=page, page_size=page_size, columns=cols,
    )
    res["as_of"] = state.screener_built_at
    res["universe"] = len(state.profiles)
    res["fixture_mode"] = state.fetchers.fixture
    return res


@router.get("/screener/facets")
def screener_facets(state: AppState = Depends(get_state)):
    out = facets(state.screener_rows)
    out["default_columns"] = [k for k in SCREENABLE if k in ("market_cap", "pe", "peg", "pb", "dividend_yield", "roe")]
    return out
