"""Deterministic synthetic data in the exact shape of the real providers' responses.

Used only in GUFU_FIXTURE_MODE (no network). It lets the whole stack run offline, and the builder
helpers are reused by the test-suite to construct hand-tuned companyfacts documents.
Values are clearly fake: they exist to exercise the parsing and metric code paths, not to inform.
"""

from __future__ import annotations

import calendar
import hashlib
import math
import random
from datetime import date, timedelta

# ---------------------------------------------------------------------------------------------
# low-level companyfacts builder
# ---------------------------------------------------------------------------------------------


class FactsBuilder:
    """Accumulates facts into the companyfacts JSON layout."""

    def __init__(self, cik: int, entity_name: str):
        self.doc: dict = {"cik": cik, "entityName": entity_name, "facts": {"us-gaap": {}, "dei": {}}}

    def add(
        self, tag: str, val: float, end: date, *, start: date | None = None, unit: str = "USD",
        form: str = "10-Q", filed: date | None = None, accn: str | None = None, frame: str | None = None,
        fy: int | None = None, fp: str | None = None, taxonomy: str = "us-gaap",
    ) -> None:
        filed = filed or (end + timedelta(days=35))
        node = self.doc["facts"][taxonomy].setdefault(tag, {"label": tag, "description": tag, "units": {}})
        series = node["units"].setdefault(unit, [])
        fact = {
            "end": end.isoformat(), "val": val, "accn": accn or f"0000000000-{filed.year % 100:02d}-{len(series):06d}",
            "fy": fy or end.year, "fp": fp or "FY", "form": form, "filed": filed.isoformat(),
        }
        if start is not None:
            fact["start"] = start.isoformat()
        if frame:
            fact["frame"] = frame
        series.append(fact)


def month_end(y: int, m: int) -> date:
    return date(y, m, calendar.monthrange(y, m)[1])


def shift(d: date, months: int) -> date:
    idx = d.year * 12 + d.month - 1 + months
    return month_end(idx // 12, idx % 12 + 1)


# ---------------------------------------------------------------------------------------------
# generic synthetic company
# ---------------------------------------------------------------------------------------------


def _rng(seed: str) -> random.Random:
    return random.Random(int(hashlib.sha256(seed.encode()).hexdigest()[:12], 16))


def synthetic_companyfacts(ticker: str, cik: int, name: str = "", years: int = 14, fye_month: int | None = None,
                           last_fy_end_year: int | None = None, bank: bool = False) -> dict:
    rng = _rng(f"facts:{ticker}")
    today = date.today()
    fye_month = fye_month or rng.choice([12, 12, 12, 12, 9, 6, 3, 1])
    if last_fy_end_year is None:
        last_fy_end_year = today.year if month_end(today.year, fye_month) + timedelta(days=60) < today else today.year - 1
    b = FactsBuilder(cik, name or f"{ticker} Corp")

    base_rev = 10 ** rng.uniform(9.3, 11.5)  # $2B .. $300B
    growth = rng.uniform(-0.02, 0.18)
    net_margin = rng.uniform(0.04, 0.30)
    gm = rng.uniform(0.25, 0.75)
    shares0 = base_rev / rng.uniform(20, 200)
    share_drift = rng.uniform(-0.04, 0.01)
    dps_ratio = rng.choice([0.0, 0.0, 0.2, 0.35, 0.5])
    assets_mult = rng.uniform(0.8, 2.5) if not bank else rng.uniform(8, 14)
    debt_ratio = rng.uniform(0.0, 0.6)

    first_fy_end = month_end(last_fy_end_year - years + 1, fye_month)
    for i in range(years):
        fy_end = shift(first_fy_end, 12 * i)
        fy_start = shift(fy_end, -12) + timedelta(days=1)
        rev_fy = base_rev * (1 + growth) ** i * rng.uniform(0.97, 1.03)
        shares = shares0 * (1 + share_drift) ** i
        ni_fy = rev_fy * net_margin * rng.uniform(0.85, 1.15)
        opinc_fy = ni_fy / 0.79 * 1.05
        dna_fy = rev_fy * 0.04
        ocf_fy = ni_fy * rng.uniform(1.05, 1.45)
        capex_fy = rev_fy * rng.uniform(0.02, 0.08)
        div_fy = ni_fy * dps_ratio
        qs = [rng.uniform(0.2, 0.3) for _ in range(4)]
        qs = [q / sum(qs) for q in qs]

        ytd_ocf = ytd_capex = ytd_div = 0.0
        for qi in range(4):
            q_end = shift(fy_start - timedelta(days=1), 3 * (qi + 1))
            q_start = shift(q_end, -3) + timedelta(days=1)
            is_k = qi == 3
            form = "10-K" if is_k else "10-Q"
            filed = q_end + timedelta(days=55 if is_k else 33)
            if filed > today:
                continue
            frac = qs[qi]
            rev_q, ni_q, op_q = rev_fy * frac, ni_fy * frac, opinc_fy * frac
            common = dict(form=form, filed=filed, fy=fy_end.year, fp="FY" if is_k else f"Q{qi + 1}")
            # discrete quarter income statement
            if not bank:
                b.add("RevenueFromContractWithCustomerExcludingAssessedTax", round(rev_q), q_end, start=q_start, **common)
                b.add("CostOfRevenue", round(rev_q * (1 - gm)), q_end, start=q_start, **common)
                b.add("OperatingIncomeLoss", round(op_q), q_end, start=q_start, **common)
            else:
                b.add("RevenuesNetOfInterestExpense", round(rev_q), q_end, start=q_start, **common)
            b.add("IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                  round(ni_q / 0.79), q_end, start=q_start, **common)
            b.add("IncomeTaxExpenseBenefit", round(ni_q / 0.79 * 0.21), q_end, start=q_start, **common)
            b.add("InterestExpenseNonoperating", round(op_q * 0.05), q_end, start=q_start, **common)
            b.add("NetIncomeLoss", round(ni_q), q_end, start=q_start, **common)
            b.add("EarningsPerShareDiluted", round(ni_q / shares, 2), q_end, start=q_start, unit="USD/shares", **common)
            b.add("WeightedAverageNumberOfDilutedSharesOutstanding", round(shares), q_end, start=q_start, unit="shares", **common)
            if dps_ratio:
                b.add("CommonStockDividendsPerShareDeclared", round(div_fy / 4 / shares, 2), q_end, start=q_start,
                      unit="USD/shares", **common)
            # cash flow: year-to-date
            ytd_ocf += ocf_fy * frac
            ytd_capex += capex_fy * frac
            ytd_div += div_fy / 4
            b.add("NetCashProvidedByUsedInOperatingActivities", round(ytd_ocf), q_end, start=fy_start, **common)
            b.add("PaymentsToAcquirePropertyPlantAndEquipment", round(ytd_capex), q_end, start=fy_start, **common)
            b.add("DepreciationDepletionAndAmortization", round(dna_fy * sum(qs[: qi + 1])), q_end, start=fy_start, **common)
            if dps_ratio:
                b.add("PaymentsOfDividendsCommonStock", round(ytd_div), q_end, start=fy_start, **common)
            b.add("PaymentsForRepurchaseOfCommonStock", round(ni_fy * 0.3 * sum(qs[: qi + 1])), q_end, start=fy_start, **common)
            # balance sheet instants
            assets = rev_fy * assets_mult * (1 + 0.01 * qi)
            equity = assets * (0.08 if bank else rng.uniform(0.3, 0.55))
            debt = assets * debt_ratio * 0.4
            b.add("Assets", round(assets), q_end, **common)
            b.add("StockholdersEquity", round(equity), q_end, **common)
            b.add("LiabilitiesAndStockholdersEquity", round(assets), q_end, **common)
            b.add("CashAndCashEquivalentsAtCarryingValue", round(assets * 0.08), q_end, **common)
            b.add("RetainedEarningsAccumulatedDeficit", round(equity * 0.7), q_end, **common)
            b.add("LongTermDebtNoncurrent", round(debt), q_end, **common)
            b.add("LongTermDebtCurrent", round(debt * 0.1), q_end, **common)
            if not bank:
                b.add("AssetsCurrent", round(assets * 0.35), q_end, **common)
                b.add("LiabilitiesCurrent", round(assets * 0.25), q_end, **common)
                b.add("InventoryNet", round(assets * 0.05), q_end, **common)
                b.add("AccountsReceivableNetCurrent", round(assets * 0.08), q_end, **common)
            b.add("EntityCommonStockSharesOutstanding", round(shares * 0.995), q_end + timedelta(days=20), unit="shares",
                  taxonomy="dei", **common)
            if is_k:
                # full-year income statement facts in the 10-K
                kc = dict(form=form, filed=filed, fy=fy_end.year, fp="FY", frame=f"CY{fy_end.year}")
                if not bank:
                    b.add("RevenueFromContractWithCustomerExcludingAssessedTax", round(rev_fy), fy_end, start=fy_start, **kc)
                    b.add("CostOfRevenue", round(rev_fy * (1 - gm)), fy_end, start=fy_start, **kc)
                    b.add("OperatingIncomeLoss", round(opinc_fy), fy_end, start=fy_start, **kc)
                else:
                    b.add("RevenuesNetOfInterestExpense", round(rev_fy), fy_end, start=fy_start, **kc)
                b.add("IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                      round(ni_fy / 0.79), fy_end, start=fy_start, **kc)
                b.add("IncomeTaxExpenseBenefit", round(ni_fy / 0.79 * 0.21), fy_end, start=fy_start, **kc)
                b.add("InterestExpenseNonoperating", round(opinc_fy * 0.05), fy_end, start=fy_start, **kc)
                b.add("NetIncomeLoss", round(ni_fy), fy_end, start=fy_start, **kc)
                b.add("EarningsPerShareDiluted", round(ni_fy / shares, 2), fy_end, start=fy_start, unit="USD/shares", **kc)
                b.add("WeightedAverageNumberOfDilutedSharesOutstanding", round(shares), fy_end, start=fy_start, unit="shares", **kc)
                if dps_ratio:
                    b.add("CommonStockDividendsPerShareDeclared", round(div_fy / shares, 2), fy_end, start=fy_start,
                          unit="USD/shares", **kc)
    return b.doc


# ---------------------------------------------------------------------------------------------
# synthetic price history in Yahoo's chart JSON layout
# ---------------------------------------------------------------------------------------------


def synthetic_chart(symbol: str, years: int = 12, end: date | None = None) -> dict:
    rng = _rng(f"px:{symbol}")
    end = end or date.today()
    start = end - timedelta(days=int(365.25 * years))
    price = 10 ** rng.uniform(1.2, 2.6)
    drift = rng.uniform(0.00015, 0.0009)
    vol = rng.uniform(0.009, 0.025)
    ts: list[int] = []
    closes: list[float | None] = []
    vols: list[int] = []
    d = start
    epoch = date(1970, 1, 1)
    while d <= end:
        if d.weekday() < 5:
            price = max(1.0, price * math.exp(drift + vol * rng.gauss(0, 1)))
            ts.append((d - epoch).days * 86400 + 14 * 3600 + 1800)
            closes.append(round(price, 2))
            vols.append(int(rng.uniform(1e6, 5e7)))
        d += timedelta(days=1)
    # a holiday hole like the real API has
    if len(closes) > 10:
        closes[5] = None
        vols[5] = 0
    valid = [c for c in closes if c is not None]
    last = valid[-1]
    year_ago = [c for c, t in zip(closes, ts, strict=False) if c is not None and t >= ts[-1] - 365 * 86400]
    return {
        "chart": {
            "result": [
                {
                    "meta": {
                        "currency": "USD", "symbol": symbol, "exchangeName": "NMS", "instrumentType": "EQUITY",
                        "regularMarketPrice": last, "chartPreviousClose": valid[0], "previousClose": valid[-2],
                        "regularMarketTime": ts[-1], "fiftyTwoWeekHigh": max(year_ago), "fiftyTwoWeekLow": min(year_ago),
                        "regularMarketDayHigh": round(last * 1.01, 2), "regularMarketDayLow": round(last * 0.99, 2),
                        "regularMarketVolume": vols[-1], "longName": f"{symbol} (synthetic)",
                    },
                    "timestamp": ts,
                    "indicators": {
                        "quote": [{"close": closes, "open": closes, "high": closes, "low": closes, "volume": vols}],
                        "adjclose": [{"adjclose": closes}],
                    },
                }
            ],
            "error": None,
        }
    }


def synthetic_company_tickers(profiles: list[tuple[str, str]]) -> dict:
    """SEC company_tickers.json layout: {"0": {"cik_str":..., "ticker":..., "title":...}, ...}"""
    out = {}
    for i, (ticker, name) in enumerate(profiles):
        out[str(i)] = {"cik_str": 1_000_000 + i, "ticker": ticker.replace(".", "-"), "title": name}
    return out
