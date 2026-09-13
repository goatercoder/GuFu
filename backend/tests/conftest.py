"""Hand-built companyfacts documents with known numbers, so tests can assert exact results."""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gufu.fetch.synthetic import FactsBuilder  # noqa: E402

# A September fiscal-year company ("Fruit Inc") with three fiscal years FY2022..FY2024.
# Quarter ends: Dec, Mar, Jun, Sep. Income statement reported as discrete quarters + FY in the 10-K;
# cash flow reported year-to-date (Q1, H1, 9M, FY) — exactly like real 10-Qs.
FYS = {
    2022: dict(rev=[100, 90, 80, 90], ni=[20, 18, 16, 18], ocf_ytd=[30, 55, 75, 100], capex_ytd=[5, 10, 15, 20],
               eps=[1.0, 0.9, 0.8, 0.9], shares=20.0, assets=[300, 305, 310, 320], equity=[120, 125, 130, 140],
               div_ytd=[2, 4, 6, 8]),
    2023: dict(rev=[110, 100, 90, 100], ni=[22, 20, 18, 20], ocf_ytd=[35, 60, 85, 110], capex_ytd=[5, 10, 15, 22],
               eps=[1.16, 1.05, 0.95, 1.05], shares=19.0, assets=[330, 335, 340, 350], equity=[145, 150, 155, 160],
               div_ytd=[2.5, 5, 7.5, 10]),
    2024: dict(rev=[120, 110, 100, 110], ni=[25, 22, 20, 23], ocf_ytd=[40, 70, 95, 125], capex_ytd=[6, 12, 18, 25],
               eps=[1.39, 1.22, 1.11, 1.28], shares=18.0, assets=[360, 365, 370, 380], equity=[165, 170, 175, 180],
               div_ytd=[3, 6, 9, 12]),
}
M = 1_000_000


def q_dates(fy: int):
    """(start, end) of the 4 fiscal quarters of a September FY, with 52/53-week style ends."""
    ends = [date(fy - 1, 12, 31), date(fy, 3, 30), date(fy, 6, 29), date(fy, 9, 28)]
    starts = [date(fy - 1, 9, 29), date(fy, 1, 1), date(fy, 3, 31), date(fy, 6, 30)]
    return list(zip(starts, ends, strict=True))


def build_fruit(restate: bool = True, tag_switch: bool = True) -> dict:
    b = FactsBuilder(cik=320193, entity_name="Fruit Inc.")
    for fy, d in FYS.items():
        qd = q_dates(fy)
        fy_start = qd[0][0]
        for qi, (qs, qe) in enumerate(qd):
            is_k = qi == 3
            form = "10-K" if is_k else "10-Q"
            filed = qe + timedelta(days=35)
            accn = f"{fy}-{qi}"
            c = dict(form=form, filed=filed, accn=accn, fy=fy, fp="FY" if is_k else f"Q{qi + 1}")
            # revenue tag switched in FY2023 (ASC 606 style): older years used 'Revenues'
            rev_tag = "Revenues" if (tag_switch and fy <= 2022) else "RevenueFromContractWithCustomerExcludingAssessedTax"
            b.add(rev_tag, d["rev"][qi] * M, qe, start=qs, **c)
            b.add("CostOfRevenue", d["rev"][qi] * M * 0.6, qe, start=qs, **c)
            b.add("OperatingIncomeLoss", d["ni"][qi] * M * 1.3, qe, start=qs, **c)
            b.add("NetIncomeLoss", d["ni"][qi] * M, qe, start=qs, **c)
            b.add("EarningsPerShareDiluted", d["eps"][qi], qe, start=qs, unit="USD/shares", **c)
            b.add("WeightedAverageNumberOfDilutedSharesOutstanding", d["shares"] * M, qe, start=qs, unit="shares", **c)
            b.add("InterestExpense", 1 * M, qe, start=qs, **c)
            b.add("IncomeTaxExpenseBenefit", d["ni"][qi] * M * 0.2, qe, start=qs, **c)
            b.add("IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                  d["ni"][qi] * M * 1.2, qe, start=qs, **c)
            # YTD cash-flow items
            b.add("NetCashProvidedByUsedInOperatingActivities", d["ocf_ytd"][qi] * M, qe, start=fy_start, **c)
            b.add("PaymentsToAcquirePropertyPlantAndEquipment", d["capex_ytd"][qi] * M, qe, start=fy_start, **c)
            b.add("PaymentsOfDividendsCommonStock", d["div_ytd"][qi] * M, qe, start=fy_start, **c)
            b.add("DepreciationDepletionAndAmortization", 3 * (qi + 1) * M, qe, start=fy_start, **c)
            # balance sheet
            b.add("Assets", d["assets"][qi] * M, qe, **c)
            b.add("StockholdersEquity", d["equity"][qi] * M, qe, **c)
            b.add("LiabilitiesAndStockholdersEquity", d["assets"][qi] * M, qe, **c)
            b.add("AssetsCurrent", 100 * M, qe, **c)
            b.add("LiabilitiesCurrent", 80 * M, qe, **c)
            b.add("CashAndCashEquivalentsAtCarryingValue", 40 * M, qe, **c)
            b.add("LongTermDebtNoncurrent", 50 * M, qe, **c)
            b.add("LongTermDebtCurrent", 5 * M, qe, **c)
            b.add("CommercialPaper", 3 * M, qe, **c)
            b.add("RetainedEarningsAccumulatedDeficit", 60 * M, qe, **c)
            b.add("InventoryNet", 10 * M, qe, **c)
            b.add("AccountsReceivableNetCurrent", 20 * M, qe, **c)
            # two share classes on the cover page, dated after period end
            b.add("EntityCommonStockSharesOutstanding", 15 * M, qe + timedelta(days=20), unit="shares", taxonomy="dei", **c)
            b.add("EntityCommonStockSharesOutstanding", 3 * M, qe + timedelta(days=20), unit="shares", taxonomy="dei", **c)
            if is_k:
                k = dict(form=form, filed=filed, accn=accn, fy=fy, fp="FY", frame=f"CY{fy}")
                b.add(rev_tag, sum(d["rev"]) * M, qe, start=fy_start, **k)
                b.add("CostOfRevenue", sum(d["rev"]) * M * 0.6, qe, start=fy_start, **k)
                b.add("OperatingIncomeLoss", sum(d["ni"]) * M * 1.3, qe, start=fy_start, **k)
                b.add("NetIncomeLoss", sum(d["ni"]) * M, qe, start=fy_start, **k)
                b.add("EarningsPerShareDiluted", round(sum(d["eps"]), 2), qe, start=fy_start, unit="USD/shares", **k)
                b.add("WeightedAverageNumberOfDilutedSharesOutstanding", d["shares"] * M, qe, start=fy_start, unit="shares", **k)
                b.add("InterestExpense", 4 * M, qe, start=fy_start, **k)
                b.add("IncomeTaxExpenseBenefit", sum(d["ni"]) * M * 0.2, qe, start=fy_start, **k)
                b.add("IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                      sum(d["ni"]) * M * 1.2, qe, start=fy_start, **k)
                b.add("CommonStockDividendsPerShareDeclared", 0.5, qe, start=fy_start, unit="USD/shares", **k)
    if restate:
        # FY2022 annual revenue restated in the FY2023 10-K (later filing, same period) -> must win
        b.add("RevenueFromContractWithCustomerExcludingAssessedTax", 361 * M, date(2022, 9, 28), start=date(2021, 9, 29),
              form="10-K", filed=date(2023, 11, 2), accn="2023-3", fy=2023, fp="FY")
        # and a stale duplicate with an OLDER filed date that must lose
        b.add("NetIncomeLoss", 999 * M, date(2022, 9, 28), start=date(2021, 9, 29), form="10-K",
              filed=date(2022, 10, 1), accn="old", fy=2022, fp="FY")
    return b.doc


def build_bank() -> dict:
    """A December FY bank: no COGS / inventory / current assets, revenue net of interest expense."""
    b = FactsBuilder(cik=19617, entity_name="Big Bank")
    for fy in (2022, 2023, 2024):
        fy_start = date(fy, 1, 1)
        ends = [date(fy, 3, 31), date(fy, 6, 30), date(fy, 9, 30), date(fy, 12, 31)]
        starts = [date(fy, 1, 1), date(fy, 4, 1), date(fy, 7, 1), date(fy, 10, 1)]
        for qi, (qs, qe) in enumerate(zip(starts, ends, strict=True)):
            is_k = qi == 3
            c = dict(form="10-K" if is_k else "10-Q", filed=qe + timedelta(days=40), accn=f"b{fy}-{qi}", fy=fy)
            b.add("RevenuesNetOfInterestExpense", 40_000 * M, qe, start=qs, **c)
            b.add("NetIncomeLoss", 12_000 * M, qe, start=qs, **c)
            b.add("EarningsPerShareDiluted", 4.0, qe, start=qs, unit="USD/shares", **c)
            b.add("NetCashProvidedByUsedInOperatingActivities", 10_000 * M * (qi + 1), qe, start=fy_start, **c)
            b.add("Assets", 3_900_000 * M, qe, **c)
            b.add("StockholdersEquity", 320_000 * M, qe, **c)
            b.add("Liabilities", 3_580_000 * M, qe, **c)
            b.add("CashAndDueFromBanks", 25_000 * M, qe, **c)
            b.add("LongTermDebt", 400_000 * M, qe, **c)
            b.add("EntityCommonStockSharesOutstanding", 2_900 * M, qe + timedelta(days=15), unit="shares", taxonomy="dei", **c)
            if is_k:
                k = dict(form="10-K", filed=qe + timedelta(days=40), accn=f"b{fy}-3", fy=fy, frame=f"CY{fy}")
                b.add("RevenuesNetOfInterestExpense", 160_000 * M, qe, start=fy_start, **k)
                b.add("NetIncomeLoss", 48_000 * M, qe, start=fy_start, **k)
                b.add("EarningsPerShareDiluted", 16.0, qe, start=fy_start, unit="USD/shares", **k)
    return b.doc


@pytest.fixture
def fruit_doc() -> dict:
    return build_fruit()


@pytest.fixture
def bank_doc() -> dict:
    return build_bank()


@pytest.fixture
def today() -> date:
    return date(2025, 1, 15)
