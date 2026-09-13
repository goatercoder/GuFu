from datetime import date

from gufu.metrics.scores import altman_z, piotroski_f
from gufu.xbrl.models import PeriodRow


def row(fy, **vals):
    return PeriodRow(key=f"{fy}-12", end=date(fy, 12, 31), start=date(fy, 1, 1), fiscal_year=fy, fiscal_quarter=None,
                     form="10-K", filed=date(fy + 1, 2, 1), values=vals)


def test_piotroski_all_pass():
    prev = row(2023, net_income=10, ocf=12, total_assets=100, long_term_debt=30, current_assets=50, current_liabilities=40,
               shares_diluted=100, gross_profit=40, revenue=100)
    cur = row(2024, net_income=15, ocf=20, total_assets=105, long_term_debt=25, current_assets=60, current_liabilities=40,
              shares_diluted=95, gross_profit=50, revenue=120)
    f = piotroski_f(cur, prev)
    assert f["score"] == 9
    assert all(t["passed"] for t in f["tests"])


def test_piotroski_missing_inputs_fail_gracefully():
    cur = row(2024, net_income=-5, ocf=None, total_assets=100)
    f = piotroski_f(cur, None)
    assert f["score"] == 0
    assert f["tests"][1]["available"] is False


def test_altman_zones():
    ttm = row(2024, operating_income=30, revenue=200)
    bal = row(2024, total_assets=100, total_liabilities=50, working_capital=20, retained_earnings=30)
    z = altman_z(ttm, bal, market_cap=150)
    # 1.2*0.2 + 1.4*0.3 + 3.3*0.3 + 0.6*3 + 2.0 = 0.24+0.42+0.99+1.8+2.0 = 5.45
    assert abs(z["value"] - 5.45) < 1e-9
    assert z["zone"] == "safe"
    weak = altman_z(row(2024, operating_income=-10, revenue=50), row(2024, total_assets=100, total_liabilities=90,
                                                                     working_capital=-10, retained_earnings=-40), 10)
    assert weak["zone"] == "distress"
    assert altman_z(ttm, bal, None) is None
