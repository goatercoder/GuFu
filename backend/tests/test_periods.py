from datetime import date

from gufu.xbrl import periods as P


def test_period_key_snaps_to_month_end():
    assert P.period_key(date(2024, 9, 28)) == "2024-09"
    assert P.period_key(date(2024, 9, 30)) == "2024-09"
    assert P.period_key(date(2024, 10, 1)) == "2024-09"  # 53-week year spills into October
    assert P.period_key(date(2025, 1, 3)) == "2024-12"
    assert P.period_key(date(2025, 1, 31)) == "2025-01"


def test_classify_duration():
    assert P.classify_duration(date(2024, 1, 1), date(2024, 3, 31)) == P.Q
    assert P.classify_duration(date(2024, 1, 1), date(2024, 6, 30)) == P.H
    assert P.classify_duration(date(2024, 1, 1), date(2024, 9, 30)) == P.NINE_M
    assert P.classify_duration(date(2024, 1, 1), date(2024, 12, 31)) == P.FY
    assert P.classify_duration(date(2023, 10, 1), date(2024, 9, 28)) == P.FY
    assert P.classify_duration(date(2024, 1, 1), date(2024, 2, 15)) is None


def test_key_arithmetic():
    assert P.key_minus_months("2024-03", 3) == "2023-12"
    assert P.key_minus_months("2024-12", 12) == "2023-12"
    assert P.key_minus_months("2024-01", -1) == "2024-02"


def test_fiscal_labels_september_fye():
    assert P.fiscal_year_for("2024-12", 9) == 2025  # Apple Q1 FY2025 ends Dec 2024
    assert P.fiscal_quarter_for("2024-12", 9) == 1
    assert P.fiscal_quarter_for("2025-03", 9) == 2
    assert P.fiscal_quarter_for("2025-06", 9) == 3
    assert P.fiscal_quarter_for("2025-09", 9) == 4
    assert P.fiscal_year_for("2025-09", 9) == 2025


def test_fiscal_labels_january_fye():
    assert P.fiscal_year_for("2025-01", 1) == 2025  # Walmart FY2025 ends Jan 2025
    assert P.fiscal_quarter_for("2024-04", 1) == 1
    assert P.fiscal_year_for("2024-04", 1) == 2025


def test_fiscal_labels_december_fye():
    assert P.fiscal_year_for("2024-12", 12) == 2024
    assert P.fiscal_quarter_for("2024-03", 12) == 1
    assert P.fiscal_quarter_for("2024-12", 12) == 4
