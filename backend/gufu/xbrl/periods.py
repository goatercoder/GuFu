"""Fiscal period arithmetic for XBRL facts.

Companyfacts `fy`/`fp` describe the *filing*, not the fact, so a 10-K's prior-year comparatives carry
the wrong labels. Everything here is driven by the fact's own start/end dates.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta

Q, H, NINE_M, FY = "Q", "H", "9M", "FY"
CLASS_MONTHS = {Q: 3, H: 6, NINE_M: 9, FY: 12}


def parse_date(s: str) -> date:
    return date.fromisoformat(s[:10])


def month_end(y: int, m: int) -> date:
    return date(y, m, calendar.monthrange(y, m)[1])


def period_key(end: date) -> str:
    """Snap a period end to a fiscal month key 'YYYY-MM'.

    Retail-style 52/53-week years end within a few days of a month boundary (e.g. Sep 28, Sep 30,
    Oct 1). Ends on or before the 15th are attributed to the previous month.
    """
    if end.day <= 15:
        y, m = (end.year - 1, 12) if end.month == 1 else (end.year, end.month - 1)
    else:
        y, m = end.year, end.month
    return f"{y:04d}-{m:02d}"


def key_parts(key: str) -> tuple[int, int]:
    y, m = key.split("-")
    return int(y), int(m)


def key_minus_months(key: str, n: int) -> str:
    y, m = key_parts(key)
    idx = y * 12 + (m - 1) - n
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def key_to_date(key: str) -> date:
    y, m = key_parts(key)
    return month_end(y, m)


def classify_duration(start: date, end: date) -> str | None:
    days = (end - start).days
    if 80 <= days <= 100:
        return Q
    if 170 <= days <= 195:
        return H
    if 260 <= days <= 290:
        return NINE_M
    if 350 <= days <= 380:
        return FY
    return None


def starts_match(a: date, b: date, tolerance_days: int = 12) -> bool:
    return abs((a - b).days) <= tolerance_days


def fiscal_year_for(key: str, fye_month: int) -> int:
    """Fiscal year label: the calendar year in which the fiscal year ends."""
    y, m = key_parts(key)
    return y if m <= fye_month else y + 1


def fiscal_quarter_for(key: str, fye_month: int) -> int:
    _, m = key_parts(key)
    q = ((m - fye_month) % 12) // 3
    return 4 if q == 0 else q


def days_between(a: date, b: date) -> int:
    return abs((a - b).days)


def shift_months(d: date, n: int) -> date:
    idx = d.year * 12 + (d.month - 1) + n
    y, m = idx // 12, idx % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


__all__ = [
    "Q", "H", "NINE_M", "FY", "CLASS_MONTHS", "parse_date", "month_end", "period_key", "key_parts",
    "key_minus_months", "key_to_date", "classify_duration", "starts_match", "fiscal_year_for",
    "fiscal_quarter_for", "days_between", "shift_months", "timedelta",
]
