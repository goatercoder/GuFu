"""Growth helpers. All return None instead of raising when data is missing or signs flip."""

from __future__ import annotations

from gufu.xbrl.models import PeriodRow


def safe_div(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


def cagr(v0: float | None, v1: float | None, years: float) -> float | None:
    """Compound annual growth from v0 to v1 over `years`. Undefined when either end is non-positive."""
    if v0 is None or v1 is None or years <= 0 or v0 <= 0 or v1 <= 0:
        return None
    return (v1 / v0) ** (1.0 / years) - 1.0


def annual_series(rows: list[PeriodRow], field: str) -> list[tuple[int, float]]:
    return [(r.fiscal_year, r.values[field]) for r in rows if r.values.get(field) is not None]


def growth_over(rows: list[PeriodRow], field: str, years: int) -> float | None:
    """CAGR of `field` between the latest annual row and the row `years` fiscal years earlier."""
    series = annual_series(rows, field)
    if len(series) < years + 1:
        return None
    fy1, v1 = series[-1]
    target_fy = fy1 - years
    match = [v for fy, v in series if fy == target_fy]
    if not match:
        return None
    return cagr(match[0], v1, years)


def ttm_yoy(quarterly: list[PeriodRow], field: str) -> float | None:
    """TTM sum vs. the TTM sum ending four quarters earlier (needs 8 consecutive quarters)."""
    vals = [r.values.get(field) for r in quarterly[-8:]]
    if len(vals) < 8 or any(v is None for v in vals):
        return None
    cur = sum(vals[4:])  # type: ignore[arg-type]
    prev = sum(vals[:4])  # type: ignore[arg-type]
    if prev <= 0 or cur <= 0:
        return None
    return cur / prev - 1.0
