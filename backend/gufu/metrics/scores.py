"""Altman Z-score and Piotroski F-score."""

from __future__ import annotations

from gufu.metrics.growth import safe_div
from gufu.xbrl.models import PeriodRow


def altman_z(ttm: PeriodRow | None, balance: PeriodRow | None, market_cap: float | None) -> dict | None:
    """Original 1968 Z-score for public manufacturers.

    Z = 1.2·WC/TA + 1.4·RE/TA + 3.3·EBIT/TA + 0.6·MarketCap/TL + 1.0·Sales/TA
    """
    if ttm is None or balance is None or market_cap is None:
        return None
    b, t = balance.values, ttm.values
    ta = b.get("total_assets")
    tl = b.get("total_liabilities")
    wc = b.get("working_capital")
    re = b.get("retained_earnings")
    ebit = t.get("operating_income")
    sales = t.get("revenue")
    if not ta or tl is None or tl == 0 or None in (wc, re, ebit, sales):
        return None
    z = 1.2 * wc / ta + 1.4 * re / ta + 3.3 * ebit / ta + 0.6 * market_cap / tl + 1.0 * sales / ta  # type: ignore[operator]
    zone = "safe" if z > 2.99 else ("grey" if z >= 1.81 else "distress")
    return {
        "value": z,
        "zone": zone,
        "components": {
            "working_capital_to_assets": wc / ta,  # type: ignore[operator]
            "retained_earnings_to_assets": re / ta,  # type: ignore[operator]
            "ebit_to_assets": ebit / ta,  # type: ignore[operator]
            "market_cap_to_liabilities": market_cap / tl,
            "sales_to_assets": sales / ta,  # type: ignore[operator]
        },
    }


def piotroski_f(cur: PeriodRow | None, prev: PeriodRow | None) -> dict | None:
    """Nine tests comparing the latest fiscal year with the prior one. Missing inputs fail the test."""
    if cur is None:
        return None
    c = cur.values
    p = prev.values if prev else {}

    def g(d, k):
        return d.get(k)

    roa_c = safe_div(g(c, "net_income"), g(c, "total_assets"))
    roa_p = safe_div(g(p, "net_income"), g(p, "total_assets"))
    lev_c = safe_div(g(c, "long_term_debt"), g(c, "total_assets"))
    lev_p = safe_div(g(p, "long_term_debt"), g(p, "total_assets"))
    cr_c = safe_div(g(c, "current_assets"), g(c, "current_liabilities"))
    cr_p = safe_div(g(p, "current_assets"), g(p, "current_liabilities"))
    gm_c = safe_div(g(c, "gross_profit"), g(c, "revenue"))
    gm_p = safe_div(g(p, "gross_profit"), g(p, "revenue"))
    at_c = safe_div(g(c, "revenue"), g(c, "total_assets"))
    at_p = safe_div(g(p, "revenue"), g(p, "total_assets"))
    sh_c, sh_p = g(c, "shares_diluted"), g(p, "shares_diluted")
    ni, ocf = g(c, "net_income"), g(c, "ocf")

    def cmp(a, b, op):
        if a is None or b is None:
            return None
        return op(a, b)

    tests = [
        ("Positive net income", ni is not None and ni > 0 if ni is not None else None, "Net income > 0"),
        ("Positive operating cash flow", ocf > 0 if ocf is not None else None, "Operating cash flow > 0"),
        ("ROA improved", cmp(roa_c, roa_p, lambda a, b: a > b), "Return on assets higher than prior year"),
        ("Cash flow exceeds earnings", cmp(ocf, ni, lambda a, b: a > b), "Operating cash flow > net income (earnings quality)"),
        ("Leverage fell", (cmp(lev_c, lev_p, lambda a, b: a <= b) if (lev_c is not None or lev_p is not None)
                           else (True if prev and "total_assets" in p else None)),
         "Long-term debt / assets did not increase"),
        ("Liquidity improved", cmp(cr_c, cr_p, lambda a, b: a > b), "Current ratio higher than prior year"),
        ("No dilution", cmp(sh_c, sh_p, lambda a, b: a <= b), "Diluted share count did not grow"),
        ("Gross margin improved", cmp(gm_c, gm_p, lambda a, b: a > b), "Gross margin higher than prior year"),
        ("Asset turnover improved", cmp(at_c, at_p, lambda a, b: a > b), "Revenue / assets higher than prior year"),
    ]
    out = []
    score = 0
    for name, passed, detail in tests:
        ok = bool(passed)
        score += int(ok)
        out.append({"name": name, "passed": ok, "available": passed is not None, "detail": detail})
    return {"score": score, "tests": out, "fiscal_year": cur.fiscal_year, "prior_fiscal_year": prev.fiscal_year if prev else None}
