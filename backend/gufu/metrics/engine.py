"""Compute every GuFu metric for one company from normalized financials + a price quote."""

from __future__ import annotations

from dataclasses import dataclass, field

from gufu.metrics import dcf as D
from gufu.metrics.definitions import GROUP_LABELS, GROUP_ORDER, METRIC_DEFS, color_for
from gufu.metrics.growth import growth_over, safe_div, ttm_yoy
from gufu.metrics.scores import altman_z, piotroski_f
from gufu.xbrl.models import Financials, PeriodRow


@dataclass
class Quote:
    price: float | None
    prev_close: float | None = None
    high52: float | None = None
    low52: float | None = None
    as_of: str | None = None
    currency: str = "USD"
    stale: bool = False
    extra: dict = field(default_factory=dict)

    @property
    def change(self) -> float | None:
        if self.price is None or self.prev_close is None:
            return None
        return self.price - self.prev_close

    @property
    def change_pct(self) -> float | None:
        if self.price is None or not self.prev_close:
            return None
        return self.price / self.prev_close - 1.0

    def to_dict(self) -> dict:
        return {
            "price": self.price, "prev_close": self.prev_close, "change": self.change, "change_pct": self.change_pct,
            "high52": self.high52, "low52": self.low52, "as_of": self.as_of, "currency": self.currency, "stale": self.stale,
        }


def _avg(a: float | None, b: float | None) -> float | None:
    if a is None:
        return b
    if b is None:
        return a
    return (a + b) / 2.0


def _year_ago_balance(fin: Financials, latest: PeriodRow | None) -> PeriodRow | None:
    if latest is None:
        return None
    target = latest.end.replace(year=latest.end.year - 1) if latest.end.month != 2 or latest.end.day != 29 else latest.end.replace(year=latest.end.year - 1, day=28)
    candidates = [r for r in fin.quarterly + fin.annual if r.values.get("total_assets") is not None and abs((r.end - target).days) <= 45]
    if not candidates:
        return None
    return min(candidates, key=lambda r: abs((r.end - target).days))


def compute_metrics(fin: Financials, quote: Quote, sector: str = "") -> dict:
    """Return {"values": {...}, "scores": {...}, "dcf": {...}}. Every value may be None."""
    T = fin.ttm.values if fin.ttm else {}
    bal_row = fin.latest_balance
    B = bal_row.values if bal_row else {}
    B1 = _year_ago_balance(fin, bal_row)
    B1v = B1.values if B1 else {}
    A = fin.annual
    price = quote.price

    shares = B.get("shares_outstanding") or T.get("shares_diluted") or (A[-1].values.get("shares_diluted") if A else None)
    market_cap = price * shares if (price is not None and shares) else None

    eps_ttm = T.get("eps_diluted")
    if eps_ttm is None and T.get("net_income") is not None and shares:
        eps_ttm = T["net_income"] / shares
    revenue = T.get("revenue")
    net_income = T.get("net_income")
    fcf = T.get("fcf")
    op_inc = T.get("operating_income")
    ebitda = T.get("ebitda")
    equity = B.get("equity")
    total_assets = B.get("total_assets")
    total_debt = B.get("total_debt")
    cash_like = (B.get("cash") or 0.0) + (B.get("short_term_investments") or 0.0) if B.get("cash") is not None else None

    ev = None
    if market_cap is not None:
        ev = market_cap + (total_debt or 0.0) - (cash_like or 0.0)

    m: dict[str, float | None] = {}
    m["price"] = price
    m["change_pct"] = quote.change_pct
    m["high_52w"] = quote.high52
    m["low_52w"] = quote.low52
    m["market_cap"] = market_cap
    m["enterprise_value"] = ev
    m["revenue_ttm"] = revenue
    m["net_income_ttm"] = net_income
    m["fcf_ttm"] = fcf
    m["eps_ttm"] = eps_ttm
    m["bvps"] = safe_div(equity, shares)
    m["fcf_per_share"] = safe_div(fcf, shares)
    m["revenue_per_share"] = safe_div(revenue, shares)

    # valuation
    m["pe"] = safe_div(price, eps_ttm) if (eps_ttm or 0) > 0 else None
    m["earnings_yield"] = safe_div(eps_ttm, price)
    m["ps"] = safe_div(market_cap, revenue) if (revenue or 0) > 0 else None
    m["pb"] = safe_div(market_cap, equity) if (equity or 0) > 0 else None
    m["pfcf"] = safe_div(market_cap, fcf) if (fcf or 0) > 0 else None
    m["fcf_yield"] = safe_div(fcf, market_cap)
    m["ev_ebitda"] = safe_div(ev, ebitda) if (ebitda or 0) > 0 else None
    m["ev_sales"] = safe_div(ev, revenue) if (revenue or 0) > 0 else None

    # profitability
    m["gross_margin"] = safe_div(T.get("gross_profit"), revenue)
    m["operating_margin"] = safe_div(op_inc, revenue)
    m["net_margin"] = safe_div(net_income, revenue)
    m["fcf_margin"] = safe_div(fcf, revenue)
    m["ebitda_margin"] = safe_div(ebitda, revenue)
    avg_equity = _avg(equity, B1v.get("equity"))
    avg_assets = _avg(total_assets, B1v.get("total_assets"))
    m["roe"] = safe_div(net_income, avg_equity) if (avg_equity or 0) > 0 else None
    m["roa"] = safe_div(net_income, avg_assets)
    tax_rate = safe_div(T.get("tax_expense"), T.get("pretax_income"))
    tax_rate = min(max(tax_rate, 0.0), 0.35) if tax_rate is not None else 0.21
    nopat = op_inc * (1 - tax_rate) if op_inc is not None else None

    def invested(bv: dict) -> float | None:
        if bv.get("equity") is None:
            return None
        return bv["equity"] + (bv.get("total_debt") or 0.0) - (bv.get("cash") or 0.0)

    avg_ic = _avg(invested(B), invested(B1v))
    m["roic"] = safe_div(nopat, avg_ic) if (avg_ic or 0) > 0 else None

    # strength
    m["current_ratio"] = safe_div(B.get("current_assets"), B.get("current_liabilities"))
    quick = None
    if B.get("current_liabilities") and B.get("cash") is not None:
        quick = ((B.get("cash") or 0) + (B.get("short_term_investments") or 0) + (B.get("receivables") or 0)) / B["current_liabilities"]
    m["quick_ratio"] = quick
    m["debt_to_equity"] = safe_div(total_debt, equity) if (equity or 0) > 0 else None
    m["debt_to_ebitda"] = safe_div(total_debt, ebitda) if (ebitda or 0) > 0 else None
    m["equity_to_assets"] = safe_div(equity, total_assets)
    ie = T.get("interest_expense")
    m["interest_coverage"] = safe_div(op_inc, ie) if (ie or 0) > 0 else None
    m["cash_to_debt"] = safe_div(cash_like, total_debt) if (total_debt or 0) > 0 else None

    # growth
    for fld, key in (("revenue", "revenue_growth"), ("eps_diluted", "eps_growth")):
        for yrs in (1, 3, 5, 10):
            m[f"{key}_{yrs}y"] = growth_over(A, fld, yrs)
    m["revenue_growth_ttm"] = ttm_yoy(fin.quarterly, "revenue")
    m["net_income_growth_5y"] = growth_over(A, "net_income", 5)
    m["fcf_growth_5y"] = growth_over(A, "fcf", 5)
    m["ocf_growth_5y"] = growth_over(A, "ocf", 5)
    m["ebitda_growth_5y"] = growth_over(A, "ebitda", 5)
    sh_g = growth_over(A, "shares_diluted", 5)
    m["shares_growth_5y"] = sh_g
    m["dps_growth_5y"] = growth_over(A, "dps", 5) or growth_over(A, "dps_derived", 5)

    # PEG
    g_ebitda = m["ebitda_growth_5y"]
    g_eps = m["eps_growth_5y"]
    m["peg"] = safe_div(m["pe"], g_ebitda * 100) if (m["pe"] is not None and g_ebitda and g_ebitda > 0) else None
    m["peg_eps"] = safe_div(m["pe"], g_eps * 100) if (m["pe"] is not None and g_eps and g_eps > 0) else None

    # dividends & buybacks
    dps = T.get("dps")
    if dps is None and T.get("dividends_paid") is not None and shares:
        dps = T["dividends_paid"] / shares
    m["dps_ttm"] = dps
    m["dividend_yield"] = safe_div(dps, price) if dps is not None else (0.0 if T else None)
    payout = safe_div(dps, eps_ttm) if (eps_ttm or 0) > 0 and dps is not None else None
    if payout is None and T.get("dividends_paid") is not None and (net_income or 0) > 0:
        payout = T["dividends_paid"] / net_income  # type: ignore[operator]
    m["payout_ratio"] = payout
    m["buyback_yield"] = safe_div(T.get("buybacks"), market_cap) if T.get("buybacks") is not None else (0.0 if T else None)
    if m["dividend_yield"] is not None or m["buyback_yield"] is not None:
        m["shareholder_yield"] = (m["dividend_yield"] or 0.0) + (m["buyback_yield"] or 0.0)
    else:
        m["shareholder_yield"] = None

    # scores
    z = altman_z(fin.ttm, bal_row, market_cap)
    f = piotroski_f(A[-1] if A else None, A[-2] if len(A) > 1 else None)
    m["altman_z"] = z["value"] if z else None
    m["piotroski_f"] = float(f["score"]) if f else None
    if z:
        z["not_meaningful"] = sector == "Financials"

    # intrinsic value
    g1 = D.choose_growth(m["eps_growth_5y"], m["eps_growth_10y"], m["eps_growth_3y"])
    fcfps = m["fcf_per_share"]
    dcf_eps = D.dcf_two_stage(eps_ttm, g1)
    g1_fcf = D.choose_growth(m["fcf_growth_5y"], m["eps_growth_5y"])
    dcf_fcf = D.dcf_two_stage(fcfps, g1_fcf)
    m["dcf_eps"] = dcf_eps
    m["dcf_fcf"] = dcf_fcf
    m["graham_number"] = D.graham_number(eps_ttm, m["bvps"])
    m["margin_of_safety"] = D.margin_of_safety(dcf_eps, price)

    dcf_block = {
        "eps": {"value": dcf_eps, "margin_of_safety": m["margin_of_safety"], "growth": g1},
        "fcf": {"value": dcf_fcf, "margin_of_safety": D.margin_of_safety(dcf_fcf, price), "growth": g1_fcf},
        "assumptions": {
            "base_eps": eps_ttm, "base_fcf_per_share": fcfps, "discount_rate": D.DEFAULT_DISCOUNT,
            "terminal_growth": D.DEFAULT_TERMINAL_GROWTH, "stage1_years": D.DEFAULT_STAGE1_YEARS,
            "stage2_years": D.DEFAULT_STAGE2_YEARS, "growth_cap": D.GROWTH_CAP,
        },
    }

    return {
        "values": m,
        "scores": {"altman_z": z, "piotroski_f": f},
        "dcf": dcf_block,
        "inputs": {
            "shares": shares, "ttm_end": fin.ttm.end.isoformat() if fin.ttm else None,
            "ttm_basis": "annual" if fin.ttm and "ttm=annual" in fin.ttm.derived else "4q",
            "balance_end": bal_row.end.isoformat() if bal_row else None, "tax_rate": tax_rate,
            "history_from_fy": A[0].fiscal_year if A else None,
            "legacy_years_used": sum(1 for r in A if "legacy" in r.derived),
        },
    }


def grouped_metrics(values: dict[str, float | None]) -> list[dict]:
    groups: dict[str, list[dict]] = {g: [] for g in GROUP_ORDER}
    for d in METRIC_DEFS:
        groups.setdefault(d.group, []).append(
            {"key": d.key, "label": d.label, "fmt": d.fmt, "value": values.get(d.key), "color": color_for(d.key, values.get(d.key)),
             "explanation": d.explanation, "decimals": d.decimals}
        )
    return [{"group": g, "label": GROUP_LABELS.get(g, g), "items": groups[g]} for g in GROUP_ORDER if groups.get(g)]
