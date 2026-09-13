from datetime import date
from pathlib import Path

import pytest

from gufu.legacy.extract import Extraction, extract_document, extract_filing
from gufu.legacy.merge import FilingResult, legacy_rows, merge_filings, period_source
from gufu.legacy.tables import parse_document, parse_number

FIX = Path(__file__).resolve().parent.parent / "fixtures" / "legacy"
M = 1_000_000
K = 1_000


def read(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def test_parse_number():
    assert parse_number("1,234") == 1234
    assert parse_number("(1,234.5)") == -1234.5
    assert parse_number("$ 2.10") == 2.10
    assert parse_number("(126") == -126
    assert parse_number("—") is None and parse_number("n/a") is None
    assert parse_number("15.0%") is None
    assert parse_number(".40") == 0.4


def test_html_tables_years_and_scale():
    doc = parse_document(read("10k_2006.htm"))
    summary = next(t for t in doc.tables if any("Cash dividends declared" in r.label for r in t.rows))
    assert summary.years == [2006, 2005, 2004, 2003, 2002]
    assert summary.scale == 1e6
    bal = next(t for t in doc.tables if any(r.label == "Total liabilities and stockholders' equity" for r in t.rows))
    assert bal.years == [2006, 2005]
    row = next(r for r in bal.rows if r.label == "Cash and cash equivalents")
    assert row.values == [1900, 1500]  # '$' cells merged away


def test_html_2006_extraction():
    ex = extract_document(read("10k_2006.htm"))
    assert ex.sections == {"income": True, "balance": True, "cashflow": True, "summary": True}
    assert sorted(ex.years) == [2002, 2003, 2004, 2005, 2006]
    y6 = ex.years[2006]
    assert y6["revenue"] == 10_500 * M and ex.methods[2006]["revenue"] == "income"
    assert y6["cost_of_revenue"] == 6_300 * M and y6["gross_profit"] == 4_200 * M
    assert y6["rnd"] == 525 * M and y6["sga"] == 2_100 * M
    assert y6["operating_income"] == 1_575 * M
    assert y6["interest_expense"] == -126 * M or y6["interest_expense"] == 126 * M
    assert y6["pretax_income"] == 1_449 * M and y6["tax_expense"] == 399 * M
    assert y6["net_income"] == 1_050 * M
    assert y6["eps_diluted"] == 2.10 and y6["dps"] == 0.60
    assert y6["shares_diluted"] == 500 * M
    assert y6["total_assets"] == 12_400 * M and y6["cash"] == 1_900 * M and y6["inventory"] == 1_100 * M
    assert y6["current_assets"] == 5_000 * M and y6["current_liabilities"] == 2_600 * M
    assert y6["long_term_debt"] == 2_100 * M and y6["equity"] == 6_200 * M and y6["total_liabilities"] == 6_200 * M
    assert y6["goodwill"] == 2_000 * M and y6["intangibles"] == 600 * M and y6["ppe_net"] == 4_200 * M
    assert y6["ocf"] == 1_480 * M and y6["capex"] == 420 * M and y6["dna"] == 380 * M
    assert y6["buybacks"] == 300 * M and y6["dividends_paid"] == 293 * M
    # older years come from the five-year summary
    y2 = ex.years[2002]
    assert y2["revenue"] == 7_900 * M and ex.methods[2002]["revenue"] == "summary"
    assert y2["eps_diluted"] == 1.09 and y2["total_assets"] == 9_000 * M and y2["ocf"] == 830 * M
    # balance sheet for 2004 only exists in the summary
    assert ex.years[2004]["total_assets"] == 10_300 * M and ex.methods[2004]["total_assets"] == "summary"
    assert ex.years[2004]["cost_of_revenue"] == 5_500 * M  # 3-year income statement
    # the segment table after the statements must not overwrite consolidated revenue
    assert ex.years[2005]["revenue"] == 9_800 * M
    assert not ex.warnings


def test_text_1997_sgml_extraction():
    ex = extract_document(read("10k_1997.txt"))
    assert ex.sections["summary"] and ex.sections["income"] and ex.sections["balance"] and ex.sections["cashflow"]
    assert sorted(ex.years) == [1993, 1994, 1995, 1996, 1997]
    y = ex.years[1997]
    assert y["revenue"] == 2_450_300 * K
    assert y["cost_of_revenue"] == 1_470_200 * K and y["gross_profit"] == 980_100 * K
    assert y["operating_income"] == 310_200 * K and y["net_income"] == 196_000 * K
    assert y["eps_diluted"] == 1.96 and y["dps"] == 0.40
    assert y["shares_diluted"] == 100_000 * K
    assert y["total_assets"] == 2_860_000 * K and y["long_term_debt"] == 480_000 * K and y["equity"] == 1_420_000 * K
    assert y["cash"] == 410_000 * K and y["current_assets"] == 1_410_000 * K and y["working_capital"] == 610_000 * K
    assert y["ocf"] == 286_000 * K and y["capex"] == 140_000 * K and y["dividends_paid"] == 40_000 * K
    assert ex.years[1993]["net_income"] == 112_000 * K and ex.years[1993]["dps"] == 0.24
    assert ex.years[1996]["cash"] == 350_000 * K


def test_ex13_incorporated_by_reference_and_ascending_years():
    primary = extract_document(read("10k_2003_primary.htm"))
    assert primary.sections.get("summary") is False and not primary.years
    ex = extract_filing([read("10k_2003_primary.htm"), read("ex13_2003.htm")])
    assert sorted(ex.years) == [2000, 2001, 2002, 2003, 2004]
    assert ex.years[2000]["revenue"] == 1_200_000 * K and ex.years[2000]["net_income"] == -12_000 * K
    assert ex.years[2000]["eps_diluted"] == -0.12
    assert ex.years[2004]["revenue"] == 1_980_000 * K and ex.methods[2004]["revenue"] == "income"
    assert ex.years[2004]["cost_of_revenue"] == 1_306_800 * K and ex.years[2004]["tax_expense"] == 47_200 * K
    assert ex.years[2003]["long_term_debt"] == 100_000 * K
    assert "revenue" in ex.years[2001] and ex.methods[2001]["revenue"] == "summary"


def test_consistency_check_drops_unbalanced_balance_sheet():
    doc = """<html><body><p>CONSOLIDATED BALANCE SHEETS (in millions)</p><table>
    <tr><td></td><td>2005</td><td>2004</td></tr>
    <tr><td>Cash and cash equivalents</td><td>100</td><td>90</td></tr>
    <tr><td>Total assets</td><td>1,000</td><td>900</td></tr>
    <tr><td>Long-term debt</td><td>300</td><td>280</td></tr>
    <tr><td>Total stockholders' equity</td><td>400</td><td>380</td></tr>
    <tr><td>Total liabilities and stockholders' equity</td><td>1,500</td><td>900</td></tr>
    </table></body></html>"""
    ex = extract_document(doc)
    assert 2005 not in ex.years  # every 2005 field was a balance-sheet field and got dropped
    assert ex.years[2004]["total_assets"] == 900 * M
    assert any("does not balance" in w for w in ex.warnings)


def test_merge_precedence_and_rows():
    older = Extraction()
    older.put(2004, "revenue", 9_000 * M, "summary")
    older.put(2004, "net_income", 700 * M, "summary")
    older.put(2003, "revenue", 8_300 * M, "summary")
    older.put(2003, "ocf", 950 * M, "summary")
    older.put(2003, "capex", 330 * M, "summary")
    older.put(2009, "revenue", 1.0, "summary")  # overlaps XBRL -> ignored
    newer = Extraction()
    newer.put(2004, "revenue", 9_100 * M, "income")  # restated in the later filing
    newer.put(2004, "total_assets", 10_300 * M, "summary")
    results = [
        FilingResult("0000-05", "10-K", date(2005, 3, 1), 2004, "https://sec/a", older),
        FilingResult("0000-07", "10-K", date(2007, 3, 1), 2006, "https://sec/b", newer),
    ]
    data = merge_filings(320193, results, first_xbrl_fy=2009)
    assert data.years[2004]["revenue"] == 9_100 * M
    assert data.provenance[2004]["revenue"]["accn"] == "0000-07"
    assert data.years[2004]["net_income"] == 700 * M and data.provenance[2004]["net_income"]["accn"] == "0000-05"
    assert 2009 not in data.years
    rows = legacy_rows(data, fye_month=9, exclude_fys={2004})
    assert [r.fiscal_year for r in rows] == [2003]
    r = rows[0]
    assert r.key == "2003-09" and r.end == date(2003, 9, 30) and r.form == "10-K (legacy)"
    assert r.values["fcf"] == 620 * M and "legacy" in r.derived
    assert r.sources["revenue"] == "legacy:summary"
    src = period_source(data, 2004)
    assert src["accn"] == "0000-07" and set(src["methods"]) == {"income", "summary"}
    back = type(data).from_dict(data.to_dict())
    assert back.years == data.years and back.provenance[2004]["revenue"]["url"] == "https://sec/b"


@pytest.mark.parametrize("name", ["10k_2006.htm", "10k_1997.txt", "ex13_2003.htm"])
def test_fixture_documents_have_no_warnings(name):
    assert extract_document(read(name)).warnings == []
