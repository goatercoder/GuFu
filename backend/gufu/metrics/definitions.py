"""Single source of truth for every metric GuFu computes: label, group, format, thresholds, explanation.

Thresholds drive the green / red pills in the UI. `good`/`bad` are (lo, hi) ranges; None = open-ended.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class MetricDef:
    key: str
    label: str
    group: str  # valuation | profitability | strength | growth | dividend | scores | pershare | size
    fmt: str  # ratio | pct | money | int | score | price
    explanation: str
    good: tuple[float | None, float | None] | None = None
    bad: tuple[float | None, float | None] | None = None
    screenable: bool = True
    decimals: int = 2

    def to_dict(self) -> dict:
        d = asdict(self)
        d["good"] = list(self.good) if self.good else None
        d["bad"] = list(self.bad) if self.bad else None
        return d


def _m(key, label, group, fmt, explanation, good=None, bad=None, screenable=True, decimals=2):
    return MetricDef(key, label, group, fmt, explanation, good, bad, screenable, decimals)


METRIC_DEFS: list[MetricDef] = [
    # size / price
    _m("price", "Price", "size", "price", "Latest traded price (Yahoo Finance).", screenable=True),
    _m("market_cap", "Market Cap", "size", "money", "Price × shares outstanding (latest 10-Q/10-K cover page)."),
    _m("enterprise_value", "Enterprise Value", "size", "money",
       "Market cap + total debt − cash & short-term investments. What it would cost to buy the whole business."),
    _m("change_pct", "1-Day Change", "size", "pct", "Change versus the previous close.", screenable=True),
    # valuation
    _m("pe", "P/E (TTM)", "valuation", "ratio", "Price ÷ trailing-twelve-month diluted EPS. N/A when earnings are negative.",
       good=(0, 15), bad=(35, None)),
    _m("peg", "PEG", "valuation", "ratio",
       "P/E ÷ 5-year EBITDA growth rate (GuruFocus definition). Below 1 suggests growth is cheaply priced.",
       good=(0, 1), bad=(3, None)),
    _m("peg_eps", "PEG (EPS growth)", "valuation", "ratio", "P/E ÷ 5-year EPS growth rate.", good=(0, 1), bad=(3, None)),
    _m("ps", "P/S (TTM)", "valuation", "ratio", "Market cap ÷ TTM revenue.", good=(0, 2), bad=(10, None)),
    _m("pb", "P/B", "valuation", "ratio", "Market cap ÷ shareholders' equity (latest balance sheet).", good=(0, 1.5), bad=(8, None)),
    _m("pfcf", "P/FCF (TTM)", "valuation", "ratio", "Market cap ÷ TTM free cash flow (OCF − capex).", good=(0, 15), bad=(40, None)),
    _m("ev_ebitda", "EV/EBITDA", "valuation", "ratio", "Enterprise value ÷ TTM EBITDA (operating income + D&A).",
       good=(0, 10), bad=(25, None)),
    _m("ev_sales", "EV/Sales", "valuation", "ratio", "Enterprise value ÷ TTM revenue.", good=(0, 2), bad=(10, None)),
    _m("earnings_yield", "Earnings Yield", "valuation", "pct", "TTM EPS ÷ price (inverse of P/E).", good=(0.07, None), bad=(None, 0.03)),
    _m("fcf_yield", "FCF Yield", "valuation", "pct", "TTM free cash flow ÷ market cap.", good=(0.06, None), bad=(None, 0.02)),
    _m("graham_number", "Graham Number", "valuation", "price",
       "√(22.5 × EPS × book value per share). Benjamin Graham's ceiling price for a defensive investor.", screenable=False),
    _m("dcf_eps", "DCF Fair Value (EPS)", "valuation", "price",
       "Two-stage discounted earnings model: 10 years at the capped historical EPS growth rate, then 10 years at 4%, "
       "discounted at 10%.", screenable=False),
    _m("dcf_fcf", "DCF Fair Value (FCF)", "valuation", "price", "Same two-stage model applied to free cash flow per share.",
       screenable=False),
    _m("margin_of_safety", "Margin of Safety (DCF-EPS)", "valuation", "pct",
       "(DCF fair value − price) ÷ DCF fair value. Positive means the stock trades below the model's value.",
       good=(0.2, None), bad=(None, -0.2)),
    # profitability
    _m("gross_margin", "Gross Margin", "profitability", "pct", "Gross profit ÷ revenue (TTM).", good=(0.4, None), bad=(None, 0.2)),
    _m("operating_margin", "Operating Margin", "profitability", "pct", "Operating income ÷ revenue (TTM).", good=(0.2, None), bad=(None, 0.05)),
    _m("net_margin", "Net Margin", "profitability", "pct", "Net income ÷ revenue (TTM).", good=(0.15, None), bad=(None, 0.03)),
    _m("fcf_margin", "FCF Margin", "profitability", "pct", "Free cash flow ÷ revenue (TTM).", good=(0.15, None), bad=(None, 0.03)),
    _m("ebitda_margin", "EBITDA Margin", "profitability", "pct", "EBITDA ÷ revenue (TTM).", good=(0.25, None), bad=(None, 0.08)),
    _m("roe", "ROE", "profitability", "pct", "TTM net income ÷ average shareholders' equity.", good=(0.15, None), bad=(None, 0.05)),
    _m("roa", "ROA", "profitability", "pct", "TTM net income ÷ average total assets.", good=(0.08, None), bad=(None, 0.02)),
    _m("roic", "ROIC", "profitability", "pct",
       "Net operating profit after tax ÷ average invested capital (equity + debt − cash).", good=(0.12, None), bad=(None, 0.05)),
    # financial strength
    _m("current_ratio", "Current Ratio", "strength", "ratio", "Current assets ÷ current liabilities.", good=(1.5, None), bad=(None, 1.0)),
    _m("quick_ratio", "Quick Ratio", "strength", "ratio", "(Cash + short-term investments + receivables) ÷ current liabilities.",
       good=(1.0, None), bad=(None, 0.5)),
    _m("debt_to_equity", "Debt/Equity", "strength", "ratio", "Total debt ÷ shareholders' equity.", good=(0, 0.5), bad=(2.0, None)),
    _m("debt_to_ebitda", "Debt/EBITDA", "strength", "ratio", "Total debt ÷ TTM EBITDA.", good=(0, 2), bad=(5, None)),
    _m("equity_to_assets", "Equity/Assets", "strength", "ratio", "Shareholders' equity ÷ total assets.", good=(0.5, None), bad=(None, 0.15)),
    _m("interest_coverage", "Interest Coverage", "strength", "ratio", "Operating income ÷ interest expense (TTM).",
       good=(10, None), bad=(None, 3)),
    _m("cash_to_debt", "Cash/Debt", "strength", "ratio", "Cash & short-term investments ÷ total debt.", good=(1, None), bad=(None, 0.2)),
    _m("altman_z", "Altman Z-Score", "scores", "score",
       "Bankruptcy-risk score (1968 model): >2.99 safe, 1.81–2.99 grey zone, <1.81 distress. Not meaningful for financials.",
       good=(2.99, None), bad=(None, 1.81)),
    _m("piotroski_f", "Piotroski F-Score", "scores", "int",
       "Nine binary tests of profitability, leverage and efficiency versus the prior fiscal year. 8–9 strong, 0–2 weak.",
       good=(7, 9), bad=(0, 3), decimals=0),
    # growth
    _m("revenue_growth_1y", "Revenue Growth (1y)", "growth", "pct", "Latest fiscal year revenue vs. the prior year.",
       good=(0.10, None), bad=(None, 0)),
    _m("revenue_growth_3y", "Revenue Growth (3y CAGR)", "growth", "pct", "3-year compound annual growth in revenue.", good=(0.10, None), bad=(None, 0)),
    _m("revenue_growth_5y", "Revenue Growth (5y CAGR)", "growth", "pct", "5-year compound annual growth in revenue.", good=(0.10, None), bad=(None, 0)),
    _m("revenue_growth_10y", "Revenue Growth (10y CAGR)", "growth", "pct", "10-year compound annual growth in revenue.", good=(0.08, None), bad=(None, 0)),
    _m("revenue_growth_ttm", "Revenue Growth (TTM YoY)", "growth", "pct", "TTM revenue vs. the TTM a year earlier.", good=(0.10, None), bad=(None, 0)),
    _m("eps_growth_1y", "EPS Growth (1y)", "growth", "pct", "Latest fiscal year diluted EPS vs. the prior year.", good=(0.10, None), bad=(None, 0)),
    _m("eps_growth_3y", "EPS Growth (3y CAGR)", "growth", "pct", "3-year compound annual growth in diluted EPS.", good=(0.10, None), bad=(None, 0)),
    _m("eps_growth_5y", "EPS Growth (5y CAGR)", "growth", "pct", "5-year compound annual growth in diluted EPS.", good=(0.10, None), bad=(None, 0)),
    _m("eps_growth_10y", "EPS Growth (10y CAGR)", "growth", "pct", "10-year compound annual growth in diluted EPS.", good=(0.08, None), bad=(None, 0)),
    _m("net_income_growth_5y", "Net Income Growth (5y CAGR)", "growth", "pct", "5-year CAGR of net income.", good=(0.10, None), bad=(None, 0)),
    _m("fcf_growth_5y", "FCF Growth (5y CAGR)", "growth", "pct", "5-year CAGR of free cash flow.", good=(0.10, None), bad=(None, 0)),
    _m("ocf_growth_5y", "OCF Growth (5y CAGR)", "growth", "pct", "5-year CAGR of operating cash flow.", good=(0.10, None), bad=(None, 0)),
    _m("ebitda_growth_5y", "EBITDA Growth (5y CAGR)", "growth", "pct", "5-year CAGR of EBITDA (used by PEG).", good=(0.10, None), bad=(None, 0)),
    _m("shares_growth_5y", "Share Count Change (5y CAGR)", "growth", "pct",
       "Annualised change in diluted share count; negative means buybacks shrank the float.", good=(None, -0.01), bad=(0.03, None)),
    # dividend
    _m("dividend_yield", "Dividend Yield", "dividend", "pct", "TTM dividends per share ÷ price.", good=(0.03, None), bad=None),
    _m("dps_ttm", "Dividends/Share (TTM)", "dividend", "price", "Sum of the last four quarterly dividends declared per share.", screenable=False),
    _m("payout_ratio", "Payout Ratio", "dividend", "pct", "Dividends per share ÷ EPS (TTM).", good=(0, 0.6), bad=(1.0, None)),
    _m("dps_growth_5y", "Dividend Growth (5y CAGR)", "dividend", "pct", "5-year CAGR of dividends per share.", good=(0.07, None), bad=(None, 0)),
    _m("buyback_yield", "Buyback Yield", "dividend", "pct", "TTM share repurchases ÷ market cap.", good=(0.03, None), bad=None),
    _m("shareholder_yield", "Shareholder Yield", "dividend", "pct", "Dividend yield + buyback yield.", good=(0.05, None), bad=None),
    # per-share
    _m("eps_ttm", "EPS (TTM)", "pershare", "price", "Diluted earnings per share over the trailing twelve months.", screenable=True),
    _m("bvps", "Book Value/Share", "pershare", "price", "Shareholders' equity ÷ shares outstanding.", screenable=False),
    _m("fcf_per_share", "FCF/Share (TTM)", "pershare", "price", "Free cash flow ÷ shares outstanding.", screenable=False),
    _m("revenue_per_share", "Revenue/Share (TTM)", "pershare", "price", "Revenue ÷ shares outstanding.", screenable=False),
    _m("revenue_ttm", "Revenue (TTM)", "size", "money", "Trailing-twelve-month revenue.", screenable=True),
    _m("net_income_ttm", "Net Income (TTM)", "size", "money", "Trailing-twelve-month net income.", screenable=True),
    _m("fcf_ttm", "Free Cash Flow (TTM)", "size", "money", "Trailing-twelve-month free cash flow.", screenable=True),
    _m("high_52w", "52-Week High", "size", "price", "Highest price in the past 52 weeks.", screenable=False),
    _m("low_52w", "52-Week Low", "size", "price", "Lowest price in the past 52 weeks.", screenable=False),
]

METRIC_BY_KEY: dict[str, MetricDef] = {m.key: m for m in METRIC_DEFS}

GROUP_ORDER = ["valuation", "profitability", "strength", "growth", "dividend", "scores", "pershare", "size"]
GROUP_LABELS = {
    "valuation": "Valuation", "profitability": "Profitability", "strength": "Financial Strength", "growth": "Growth",
    "dividend": "Dividends & Buybacks", "scores": "Quality Scores", "pershare": "Per Share", "size": "Size & Price",
}

DEFAULT_SCREENER_COLUMNS = ["market_cap", "pe", "peg", "pb", "ps", "ev_ebitda", "dividend_yield", "roe", "roic",
                            "revenue_growth_5y", "piotroski_f", "altman_z"]


def color_for(key: str, value: float | None) -> str:
    """good | bad | neutral | na"""
    if value is None:
        return "na"
    d = METRIC_BY_KEY.get(key)
    if d is None:
        return "neutral"

    def within(rng):
        lo, hi = rng
        return (lo is None or value >= lo) and (hi is None or value <= hi)

    if d.good and within(d.good):
        return "good"
    if d.bad and within(d.bad):
        return "bad"
    return "neutral"
