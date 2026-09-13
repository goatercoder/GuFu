from datetime import date

import pytest

from gufu.metrics.engine import Quote, compute_metrics, grouped_metrics
from gufu.xbrl.normalize import normalize
from tests.conftest import FYS, M, build_bank, build_fruit

TODAY = date(2025, 1, 15)


@pytest.fixture(scope="module")
def result():
    fin = normalize(build_fruit(), today=TODAY)
    q = Quote(price=100.0, prev_close=98.0, high52=120.0, low52=80.0)
    return fin, compute_metrics(fin, q, sector="Information Technology")


def test_market_cap_and_valuation(result):
    fin, res = result
    v = res["values"]
    shares = 18 * M  # dei classes summed
    assert v["market_cap"] == 100.0 * shares
    eps = round(sum(FYS[2024]["eps"]), 2)  # 5.0 from the 10-K FY fact
    assert v["eps_ttm"] == pytest.approx(eps)
    assert v["pe"] == pytest.approx(100 / eps)
    rev = sum(FYS[2024]["rev"]) * M
    assert v["ps"] == pytest.approx(100.0 * shares / rev)
    assert v["pb"] == pytest.approx(100.0 * shares / (180 * M))
    # EV = mcap + debt 58 - cash 40
    assert v["enterprise_value"] == pytest.approx(100.0 * shares + 58 * M - 40 * M)
    fcf = (125 - 25) * M
    assert v["pfcf"] == pytest.approx(100.0 * shares / fcf)
    assert v["fcf_yield"] == pytest.approx(fcf / (100.0 * shares))
    assert v["change_pct"] == pytest.approx(100 / 98 - 1)


def test_profitability(result):
    fin, res = result
    v = res["values"]
    rev = sum(FYS[2024]["rev"]) * M
    ni = sum(FYS[2024]["ni"]) * M
    assert v["net_margin"] == pytest.approx(ni / rev)
    assert v["gross_margin"] == pytest.approx(0.4)
    # ROE on average equity: (180 + 140) / 2 -> year-ago balance is Sep 2023 (160)
    assert v["roe"] == pytest.approx(ni / ((180 + 160) / 2 * M))
    assert v["roa"] == pytest.approx(ni / ((380 + 350) / 2 * M))
    assert v["interest_coverage"] == pytest.approx(ni * 1.3 / (4 * M))


def test_strength(result):
    _, res = result
    v = res["values"]
    assert v["current_ratio"] == pytest.approx(100 / 80)
    assert v["quick_ratio"] == pytest.approx((40 + 20) / 80)
    assert v["debt_to_equity"] == pytest.approx(58 / 180)
    assert v["equity_to_assets"] == pytest.approx(180 / 380)
    assert v["cash_to_debt"] == pytest.approx(40 / 58)


def test_growth_and_peg(result):
    _, res = result
    v = res["values"]
    r22 = 361.0  # restated FY2022 revenue
    r24 = sum(FYS[2024]["rev"])
    r23 = sum(FYS[2023]["rev"])
    assert v["revenue_growth_1y"] == pytest.approx(r24 / r23 - 1)
    # 2 years of history is not enough for a 3y CAGR
    assert v["revenue_growth_3y"] is None
    assert v["revenue_growth_5y"] is None
    assert v["peg"] is None  # needs 5y EBITDA growth
    assert r22 > 0
    eps24, eps23 = round(sum(FYS[2024]["eps"]), 2), round(sum(FYS[2023]["eps"]), 2)
    assert v["eps_growth_1y"] == pytest.approx(eps24 / eps23 - 1)


def test_dividends(result):
    _, res = result
    v = res["values"]
    assert v["dps_ttm"] == 0.5
    assert v["dividend_yield"] == pytest.approx(0.005)
    assert v["payout_ratio"] == pytest.approx(0.5 / 5.0)


def test_scores_and_dcf(result):
    _, res = result
    z = res["scores"]["altman_z"]
    assert z is not None and z["zone"] in ("safe", "grey", "distress")
    assert z["not_meaningful"] is False
    f = res["scores"]["piotroski_f"]
    assert f is not None and 0 <= f["score"] <= 9 and len(f["tests"]) == 9
    assert f["tests"][0]["passed"] is True  # positive net income
    assert f["tests"][6]["passed"] is True  # shares fell 19 -> 18
    dcf = res["dcf"]
    assert dcf["eps"]["value"] is not None and dcf["eps"]["value"] > 0
    assert dcf["assumptions"]["discount_rate"] == 0.10
    assert res["values"]["graham_number"] == pytest.approx((22.5 * 5.0 * 10) ** 0.5)


def test_grouped_output_has_colors(result):
    _, res = result
    groups = grouped_metrics(res["values"])
    names = [g["group"] for g in groups]
    assert names[:5] == ["valuation", "profitability", "strength", "growth", "dividend"]
    pe_item = next(i for g in groups if g["group"] == "valuation" for i in g["items"] if i["key"] == "pe")
    assert pe_item["color"] in ("good", "neutral", "bad")


def test_bank_does_not_crash_and_flags_z():
    fin = normalize(build_bank(), today=TODAY)
    res = compute_metrics(fin, Quote(price=200.0, prev_close=199.0), sector="Financials")
    v = res["values"]
    assert v["pe"] == pytest.approx(200 / 16.0)
    assert v["gross_margin"] is None
    assert v["current_ratio"] is None
    assert v["pb"] == pytest.approx(200.0 * 2_900 * M / (320_000 * M))
    assert res["scores"]["altman_z"] is None or res["scores"]["altman_z"]["not_meaningful"] is True


def test_no_price_gives_none_not_error():
    fin = normalize(build_fruit(), today=TODAY)
    res = compute_metrics(fin, Quote(price=None))
    assert res["values"]["pe"] is None and res["values"]["market_cap"] is None
    assert res["values"]["net_margin"] is not None
