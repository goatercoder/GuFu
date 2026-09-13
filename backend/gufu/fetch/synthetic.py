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


def company_params(ticker: str) -> dict:
    """Deterministic economic 'personality' of a synthetic company (shared by every generator)."""
    rng = _rng(f"facts:{ticker}")
    today = date.today()
    fye_month = rng.choice([12, 12, 12, 12, 9, 6, 3, 1])
    last_fy = today.year if month_end(today.year, fye_month) + timedelta(days=60) < today else today.year - 1
    return {
        "fye_month": fye_month, "last_fy": last_fy, "xbrl_years": 14,
        "base_rev": 10 ** rng.uniform(9.3, 11.5), "growth": rng.uniform(-0.02, 0.18), "net_margin": rng.uniform(0.04, 0.30),
        "gm": rng.uniform(0.25, 0.75), "shares0": None, "share_drift": rng.uniform(-0.04, 0.01),
        "dps_ratio": rng.choice([0.0, 0.0, 0.2, 0.35, 0.5]), "assets_mult": rng.uniform(0.8, 2.5), "debt_ratio": rng.uniform(0.0, 0.6),
        "anchor_fy": last_fy - 13,
    }


def annual_figures(ticker: str, fy: int, params: dict | None = None, bank: bool = False) -> dict:
    """Full-year figures for one fiscal year; consistent across XBRL and legacy generators."""
    p = params or company_params(ticker)
    i = fy - p["anchor_fy"]
    rng = _rng(f"year:{ticker}:{fy}")
    rev = p["base_rev"] * (1 + p["growth"]) ** i * rng.uniform(0.97, 1.03)
    shares0 = p["base_rev"] / 80.0
    shares = shares0 * (1 + p["share_drift"]) ** i
    ni = rev * p["net_margin"] * rng.uniform(0.85, 1.15)
    pretax = ni / 0.79
    tax = pretax * 0.21
    opinc = pretax * 1.05
    interest = opinc * 0.05
    dna = rev * 0.04
    ocf = ni * rng.uniform(1.05, 1.45)
    capex = rev * rng.uniform(0.02, 0.08)
    div = ni * p["dps_ratio"]
    buyback = ni * 0.3
    assets_mult = (p["assets_mult"] if not bank else p["assets_mult"] * 5 + 6)
    assets = rev * assets_mult
    equity = assets * (0.08 if bank else 0.30 + 0.25 * (p["gm"]))
    debt_lt = assets * p["debt_ratio"] * 0.4
    debt_st = debt_lt * 0.1
    cogs = rev * (1 - p["gm"])
    gp = rev - cogs
    rnd = rev * 0.05
    sga = gp - opinc - rnd - dna
    if sga < 0:
        sga = gp * 0.1
        opinc = gp - rnd - sga - dna
        pretax = opinc - interest
        tax = pretax * 0.21
        ni = pretax - tax
    cash = assets * 0.08
    recv = assets * 0.08
    inv = assets * 0.05
    cur_assets = assets * 0.35 if not bank else None
    cur_liab = assets * 0.25 if not bank else None
    ppe = assets * 0.30
    goodwill = assets * 0.10
    total_liab = assets - equity
    retained = equity * 0.7
    return {
        "revenue": rev, "cost_of_revenue": cogs, "gross_profit": gp, "rnd": rnd, "sga": sga, "dna": dna,
        "operating_income": opinc, "interest_expense": interest, "pretax_income": pretax, "tax_expense": tax, "net_income": ni,
        "shares": shares, "eps": ni / shares, "dps": (div / shares) if div else 0.0, "ocf": ocf, "capex": capex,
        "dividends_paid": div, "buybacks": buyback, "total_assets": assets, "equity": equity, "long_term_debt": debt_lt,
        "short_term_debt": debt_st, "cash": cash, "receivables": recv, "inventory": inv, "current_assets": cur_assets,
        "current_liabilities": cur_liab, "ppe_net": ppe, "goodwill": goodwill, "total_liabilities": total_liab,
        "retained_earnings": retained,
    }


def synthetic_companyfacts(ticker: str, cik: int, name: str = "", years: int | None = None, fye_month: int | None = None,
                           last_fy_end_year: int | None = None, bank: bool = False) -> dict:
    p = company_params(ticker)
    fye_month = fye_month or p["fye_month"]
    last_fy_end_year = last_fy_end_year or p["last_fy"]
    years = years or p["xbrl_years"]
    today = date.today()
    b = FactsBuilder(cik, name or f"{ticker} Corp")
    first_fy_end = month_end(last_fy_end_year - years + 1, fye_month)
    for i in range(years):
        fy_end = shift(first_fy_end, 12 * i)
        fy_start = shift(fy_end, -12) + timedelta(days=1)
        fyr = fy_end.year
        f = annual_figures(ticker, fyr, p, bank=bank)
        rng = _rng(f"quarters:{ticker}:{fyr}")
        rev_fy, ni_fy, opinc_fy, dna_fy = f["revenue"], f["net_income"], f["operating_income"], f["dna"]
        ocf_fy, capex_fy, div_fy, shares = f["ocf"], f["capex"], f["dividends_paid"], f["shares"]
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
            if not bank:
                b.add("RevenueFromContractWithCustomerExcludingAssessedTax", round(rev_q), q_end, start=q_start, **common)
                b.add("CostOfRevenue", round(f["cost_of_revenue"] * frac), q_end, start=q_start, **common)
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
            if div_fy:
                b.add("CommonStockDividendsPerShareDeclared", round(div_fy / 4 / shares, 2), q_end, start=q_start,
                      unit="USD/shares", **common)
            ytd_ocf += ocf_fy * frac
            ytd_capex += capex_fy * frac
            ytd_div += div_fy / 4
            b.add("NetCashProvidedByUsedInOperatingActivities", round(ytd_ocf), q_end, start=fy_start, **common)
            b.add("PaymentsToAcquirePropertyPlantAndEquipment", round(ytd_capex), q_end, start=fy_start, **common)
            b.add("DepreciationDepletionAndAmortization", round(dna_fy * sum(qs[: qi + 1])), q_end, start=fy_start, **common)
            if div_fy:
                b.add("PaymentsOfDividendsCommonStock", round(ytd_div), q_end, start=fy_start, **common)
            b.add("PaymentsForRepurchaseOfCommonStock", round(f["buybacks"] * sum(qs[: qi + 1])), q_end, start=fy_start, **common)
            assets = f["total_assets"] * (1 + 0.01 * qi)
            equity = f["equity"] * (1 + 0.01 * qi)
            b.add("Assets", round(assets), q_end, **common)
            b.add("StockholdersEquity", round(equity), q_end, **common)
            b.add("LiabilitiesAndStockholdersEquity", round(assets), q_end, **common)
            b.add("CashAndCashEquivalentsAtCarryingValue", round(f["cash"]), q_end, **common)
            b.add("RetainedEarningsAccumulatedDeficit", round(f["retained_earnings"]), q_end, **common)
            b.add("LongTermDebtNoncurrent", round(f["long_term_debt"]), q_end, **common)
            b.add("LongTermDebtCurrent", round(f["short_term_debt"]), q_end, **common)
            if not bank:
                b.add("AssetsCurrent", round(f["current_assets"]), q_end, **common)
                b.add("LiabilitiesCurrent", round(f["current_liabilities"]), q_end, **common)
                b.add("InventoryNet", round(f["inventory"]), q_end, **common)
                b.add("AccountsReceivableNetCurrent", round(f["receivables"]), q_end, **common)
            b.add("EntityCommonStockSharesOutstanding", round(shares * 0.995), q_end + timedelta(days=20), unit="shares",
                  taxonomy="dei", **common)
            if is_k:
                kc = dict(form=form, filed=filed, fy=fy_end.year, fp="FY", frame=f"CY{fy_end.year}")
                if not bank:
                    b.add("RevenueFromContractWithCustomerExcludingAssessedTax", round(rev_fy), fy_end, start=fy_start, **kc)
                    b.add("CostOfRevenue", round(f["cost_of_revenue"]), fy_end, start=fy_start, **kc)
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
                if div_fy:
                    b.add("CommonStockDividendsPerShareDeclared", round(div_fy / shares, 2), fy_end, start=fy_start,
                          unit="USD/shares", **kc)
    return b.doc


# ---------------------------------------------------------------------------------------------
# synthetic pre-XBRL filings (submissions index + old-style 10-K documents)
# ---------------------------------------------------------------------------------------------

LEGACY_YEARS_BACK = 20


def synthetic_accn(cik: int, fy: int) -> str:
    return f"{cik:010d}-{fy % 100:02d}-{fy:06d}"


def synthetic_submissions(ticker: str, cik: int) -> dict:
    p = company_params(ticker)
    first_xbrl_fy = p["last_fy"] - p["xbrl_years"] + 1
    accn, filed, report, form, primary = [], [], [], [], []
    for fy in range(first_xbrl_fy - 1, first_xbrl_fy - 1 - LEGACY_YEARS_BACK, -1):
        end = month_end(fy, p["fye_month"])
        accn.append(synthetic_accn(cik, fy))
        filed.append((end + timedelta(days=70)).isoformat())
        report.append(end.isoformat())
        form.append("10-K" if fy >= 2001 else "10-K405")
        primary.append("d10k.htm" if fy >= 2001 else "")
    return {
        "cik": str(cik), "name": f"{ticker} Corp", "fiscalYearEnd": f"{p['fye_month']:02d}28",
        "filings": {"recent": {"accessionNumber": accn, "filingDate": filed, "reportDate": report, "form": form,
                               "primaryDocument": primary, "primaryDocDescription": ["10-K"] * len(accn)}, "files": []},
    }


def _m(v: float | None, per_share: bool = False) -> str:
    if v is None:
        return "—"
    if per_share:
        s = f"{abs(v):,.2f}"
    else:
        s = f"{abs(v) / 1e6:,.1f}"
    return f"({s})" if v < 0 else s


def synthetic_10k_document(ticker: str, fy: int, fmt: str = "html", bank: bool = False, name: str = "") -> str:
    p = company_params(ticker)
    name = name or f"{ticker} Corp"
    mon = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November",
           "December"][p["fye_month"] - 1]
    yrs5 = [fy - i for i in range(5)]
    yrs3 = yrs5[:3]
    fig = {y: annual_figures(ticker, y, p, bank=bank) for y in yrs5}

    def row(label: str, key: str, years: list[int], per_share: bool = False, sign: float = 1.0) -> tuple[str, list[str]]:
        return label, [_m((fig[y][key] * sign) if fig[y].get(key) is not None else None, per_share) for y in years]

    summary = [
        row("Net sales" if not bank else "Total net revenue", "revenue", yrs5),
        row("Operating income", "operating_income", yrs5),
        row("Net income", "net_income", yrs5),
        row("Net income per share - diluted", "eps", yrs5, True),
        row("Cash dividends declared per share", "dps", yrs5, True),
        row("Total assets", "total_assets", yrs5),
        row("Long-term debt, less current portion", "long_term_debt", yrs5),
        row("Stockholders' equity", "equity", yrs5),
        row("Net cash provided by operating activities", "ocf", yrs5),
        row("Capital expenditures", "capex", yrs5),
    ]
    income = ([row("Net sales", "revenue", yrs3), row("Cost of sales", "cost_of_revenue", yrs3), row("Gross profit", "gross_profit", yrs3),
               row("Research and development", "rnd", yrs3), row("Selling, general and administrative", "sga", yrs3),
               row("Depreciation and amortization", "dna", yrs3)] if not bank else [row("Total net revenue", "revenue", yrs3)]) + [
        row("Operating income", "operating_income", yrs3), row("Interest expense", "interest_expense", yrs3, sign=-1.0),
        row("Income before income taxes", "pretax_income", yrs3), row("Provision for income taxes", "tax_expense", yrs3),
        row("Net income", "net_income", yrs3), row("Diluted earnings per share", "eps", yrs3, True),
        row("Weighted average shares outstanding - diluted", "shares", yrs3),
    ]
    yrs2 = yrs5[:2]
    balance = [row("Cash and cash equivalents", "cash", yrs2), row("Accounts receivable, net", "receivables", yrs2)] + (
        [row("Inventories", "inventory", yrs2), row("Total current assets", "current_assets", yrs2)] if not bank else []) + [
        row("Property, plant and equipment, net", "ppe_net", yrs2), row("Goodwill", "goodwill", yrs2),
        row("Total assets", "total_assets", yrs2)] + (
        [row("Total current liabilities", "current_liabilities", yrs2)] if not bank else []) + [
        row("Long-term debt", "long_term_debt", yrs2), row("Total liabilities", "total_liabilities", yrs2),
        row("Retained earnings", "retained_earnings", yrs2), row("Total stockholders' equity", "equity", yrs2),
        row("Total liabilities and stockholders' equity", "total_assets", yrs2),
    ]
    cashflow = [row("Net income", "net_income", yrs3), row("Depreciation and amortization", "dna", yrs3),
                row("Net cash provided by operating activities", "ocf", yrs3), row("Capital expenditures", "capex", yrs3, sign=-1.0),
                row("Purchases of treasury stock", "buybacks", yrs3, sign=-1.0), row("Dividends paid", "dividends_paid", yrs3, sign=-1.0)]

    if fmt == "html":
        def table(years, rows, header):
            h = "".join(f"<td>{y}</td>" for y in years)
            body = "".join(f"<tr><td>{lab}</td>{''.join(f'<td>{v}</td>' for v in vals)}</tr>" for lab, vals in rows)
            return f"<p>{header}</p><table><tr><td></td>{h}</tr>{body}</table>"
        return (
            f"<html><body><p>FORM 10-K {name} for the fiscal year ended {mon} {fy}</p>"
            f"<p>Item 6. Selected Financial Data</p>{table(yrs5, summary, '(In millions, except per share amounts)')}"
            f"<p>Item 8. Financial Statements</p><p>CONSOLIDATED STATEMENTS OF INCOME</p>{table(yrs3, income, '(In millions, except per share amounts)')}"
            f"<p>CONSOLIDATED BALANCE SHEETS</p>{table(yrs2, balance, '(In millions)')}"
            f"<p>CONSOLIDATED STATEMENTS OF CASH FLOWS</p>{table(yrs3, cashflow, '(In millions)')}</body></html>"
        )

    def ttable(years, rows, header):
        head = " " * 44 + "".join(f"{y:>12}" for y in years)
        lines = [header, head, " " * 44 + ("  " + "-" * 10) * len(years)]
        for lab, vals in rows:
            lines.append(f"{lab:<44}" + "".join(f"{v:>12}" for v in vals))
        return "\n".join(lines)

    body = (
        f"<SEC-DOCUMENT>{synthetic_accn(0, fy)}.txt\n<DOCUMENT>\n<TYPE>10-K405\n<SEQUENCE>1\n<TEXT>\n"
        f"                    FORM 10-K\n{name}\nFor the fiscal year ended {mon} {fy}\n<PAGE> 10\n"
        f"ITEM 6.  SELECTED FINANCIAL DATA\n\n{ttable(yrs5, summary, '(In millions, except per share amounts)')}\n<PAGE> 20\n"
        f"ITEM 8.  FINANCIAL STATEMENTS\n\nCONSOLIDATED STATEMENTS OF INCOME\n{ttable(yrs3, income, '(In millions, except per share amounts)')}\n<PAGE> 21\n"
        f"CONSOLIDATED BALANCE SHEETS\n{ttable(yrs2, balance, '(In millions)')}\n<PAGE> 22\n"
        f"CONSOLIDATED STATEMENTS OF CASH FLOWS\n{ttable(yrs3, cashflow, '(In millions)')}\n</TEXT>\n</DOCUMENT>\n</SEC-DOCUMENT>\n"
    )
    return body


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
