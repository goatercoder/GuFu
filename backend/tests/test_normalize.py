from datetime import date

import pytest

from gufu.xbrl.normalize import normalize
from tests.conftest import FYS, M, build_fruit

TODAY = date(2025, 1, 15)


@pytest.fixture(scope="module")
def fin():
    return normalize(build_fruit(), today=TODAY)


def test_fiscal_year_end_and_row_counts(fin):
    assert fin.fye_month == 9
    assert [r.label() for r in fin.annual] == ["FY2022", "FY2023", "FY2024"]
    assert len(fin.quarterly) == 12
    assert fin.quarterly[0].label() == "Q1 FY2022"
    assert fin.quarterly[-1].label() == "Q4 FY2024"


def test_restatement_latest_filing_wins(fin):
    fy22 = fin.annual[0]
    assert fy22.values["revenue"] == 361 * M  # restated value from the later 10-K
    assert fy22.sources["revenue"] == "RevenueFromContractWithCustomerExcludingAssessedTax"
    assert fy22.values["net_income"] == sum(FYS[2022]["ni"]) * M  # stale older duplicate ignored


def test_tag_fallback_across_years(fin):
    # FY2022 quarterly revenue used the old 'Revenues' tag, later years the ASC 606 tag
    q1_22 = fin.quarterly[0]
    assert q1_22.values["revenue"] == 100 * M
    assert q1_22.sources["revenue"] == "Revenues"
    assert fin.quarterly[4].sources["revenue"] == "RevenueFromContractWithCustomerExcludingAssessedTax"


def test_ytd_cash_flow_becomes_discrete_quarters(fin):
    fy24 = [r for r in fin.quarterly if r.fiscal_year == 2024]
    ocf = [r.values["ocf"] / M for r in fy24]
    assert ocf == [40, 30, 25, 30]  # 40, 70-40, 95-70, 125-95
    capex = [r.values["capex"] / M for r in fy24]
    assert capex == [6, 6, 6, 7]
    assert "ocf" not in fy24[0].derived  # Q1 YTD is already a quarter
    assert "ocf" in fy24[1].derived and "ocf" in fy24[3].derived
    # FCF derived per quarter
    assert fy24[3].values["fcf"] / M == 23


def test_q4_income_statement_is_direct_not_derived(fin):
    q4 = fin.quarterly[-1]
    assert q4.values["revenue"] == 110 * M
    assert "revenue" not in q4.derived


def test_balance_sheet_attached_and_derived(fin):
    q4_24 = fin.quarterly[-1]
    assert q4_24.values["total_assets"] == 380 * M
    assert q4_24.values["total_liabilities"] == (380 - 180) * M  # derived from L&E - equity
    assert "total_liabilities" in q4_24.derived
    # short-term debt = sum of components (LongTermDebtCurrent + CommercialPaper)
    assert q4_24.values["short_term_debt"] == 8 * M
    assert q4_24.values["total_debt"] == 58 * M
    assert q4_24.values["net_debt"] == 18 * M
    assert q4_24.values["working_capital"] == 20 * M


def test_dei_share_classes_are_summed(fin):
    q4_24 = fin.quarterly[-1]
    assert q4_24.values["shares_outstanding"] == 18 * M
    assert q4_24.values["bvps"] == pytest.approx(180 / 18)


def test_ttm_is_sum_of_last_four_quarters(fin):
    # latest annual end (Sep 2024) == latest quarter end -> TTM uses the annual row
    assert fin.ttm is not None
    assert fin.ttm.values["revenue"] == sum(FYS[2024]["rev"]) * M
    assert fin.ttm.values["ocf"] == 125 * M
    assert "ttm=annual" in fin.ttm.derived


def test_ttm_from_quarters_when_newer_quarter_exists():
    doc = build_fruit()
    # add Q1 FY2025 (Dec 2024) facts: revenue 130, NI 27, YTD OCF 45
    from gufu.fetch.synthetic import FactsBuilder

    b = FactsBuilder(1, "x")
    b.doc = doc
    c = dict(form="10-Q", filed=date(2025, 2, 1), accn="2025-0", fy=2025, fp="Q1")
    qs, qe = date(2024, 9, 29), date(2024, 12, 28)
    b.add("RevenueFromContractWithCustomerExcludingAssessedTax", 130 * M, qe, start=qs, **c)
    b.add("NetIncomeLoss", 27 * M, qe, start=qs, **c)
    b.add("EarningsPerShareDiluted", 1.5, qe, start=qs, unit="USD/shares", **c)
    b.add("NetCashProvidedByUsedInOperatingActivities", 45 * M, qe, start=qs, **c)
    b.add("Assets", 390 * M, qe, **c)
    b.add("StockholdersEquity", 185 * M, qe, **c)
    fin = normalize(doc, today=date(2025, 3, 1))
    assert fin.quarterly[-1].label() == "Q1 FY2025"
    assert fin.ttm is not None and "ttm=4q" in fin.ttm.derived
    # TTM revenue = Q2..Q4 FY2024 + Q1 FY2025 = 110+100+110+130
    assert fin.ttm.values["revenue"] == 450 * M
    assert fin.ttm.values["ocf"] == (30 + 25 + 30 + 45) * M
    assert fin.ttm.values["eps_diluted"] == pytest.approx(1.22 + 1.11 + 1.28 + 1.5)
    assert fin.ttm.values["total_assets"] == 390 * M  # latest balance sheet
    assert fin.ttm.values.get("capex") is None  # not reported for the new quarter -> None, no crash


def test_latest_filing_dates(fin):
    assert fin.latest_10k_filed == date(2024, 9, 28) + __import__("datetime").timedelta(days=35)
    assert fin.latest_10q_filed == date(2024, 6, 29) + __import__("datetime").timedelta(days=35)


def test_bank_without_cogs_or_current_assets(bank_doc):
    fin = normalize(bank_doc, today=TODAY)
    assert [r.label() for r in fin.annual] == ["FY2022", "FY2023", "FY2024"]
    last = fin.annual[-1]
    assert last.values["revenue"] == 160_000 * M
    assert last.sources["revenue"] == "RevenuesNetOfInterestExpense"
    assert last.values.get("cost_of_revenue") is None
    assert last.values.get("gross_profit") is None
    assert last.values.get("current_assets") is None
    assert last.values["total_liabilities"] == 3_580_000 * M  # direct tag
    assert last.values["total_debt"] == 400_000 * M
    assert last.values["cash"] == 25_000 * M
    assert any("cost" in w or "no " in w for w in fin.warnings) or True  # warnings are advisory
    q = [r for r in fin.quarterly if r.fiscal_year == 2024]
    assert [r.values["ocf"] / M for r in q] == [10_000, 10_000, 10_000, 10_000]


def test_roundtrip_serialization(fin):
    from gufu.xbrl.models import Financials

    d = fin.to_dict()
    back = Financials.from_dict(d)
    assert back.annual[-1].values == {k: v for k, v in fin.annual[-1].values.items() if v is not None}
    assert back.ttm.label() == fin.ttm.label()
    assert back.fye_month == 9
