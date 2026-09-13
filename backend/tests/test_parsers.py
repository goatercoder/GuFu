"""Parsers for the live sources, exercised on captured-format samples (the sandbox cannot reach the hosts)."""

from datetime import date

import pytest

from gufu.fetch.sec import max_filed
from gufu.fetch.synthetic import synthetic_chart
from gufu.prices import downsample, parse_stooq_csv, parse_yahoo_chart, slice_range
from gufu.universe import CompanyProfile, resolve_ciks, search_companies, stooq_symbol, yahoo_symbol

STOOQ = """Date,Open,High,Low,Close,Volume
2024-01-02,185.0,186.5,183.2,185.64,82488700
2024-01-03,184.2,185.9,183.4,184.25,58414500
2024-01-04,182.1,183.1,180.9,181.91,71983600
"""


def test_stooq_csv():
    ph = parse_stooq_csv(STOOQ, "AAPL")
    assert ph.dates == ["2024-01-02", "2024-01-03", "2024-01-04"]
    assert ph.close[-1] == 181.91
    assert ph.meta["price"] == 181.91 and ph.meta["prev_close"] == 184.25
    assert ph.meta["high52"] == 185.64 and ph.meta["low52"] == 181.91
    with pytest.raises(ValueError):
        parse_stooq_csv("No data", "ZZZ")


def test_yahoo_chart_layout_and_holiday_nulls():
    raw = synthetic_chart("AAPL", years=1, end=date(2025, 1, 10))
    ph = parse_yahoo_chart(raw, "AAPL")
    assert len(ph.dates) == len(ph.close) == len(ph.volume)
    assert all(c is not None for c in ph.close)
    assert ph.meta["price"] == raw["chart"]["result"][0]["meta"]["regularMarketPrice"]
    assert ph.meta["high52"] >= max(ph.close[-250:])
    with pytest.raises(ValueError):
        parse_yahoo_chart({"chart": {"result": None, "error": {"code": "Not Found"}}}, "ZZZ")


def test_slice_and_downsample():
    ph = parse_yahoo_chart(synthetic_chart("MSFT", years=12, end=date(2025, 6, 30)), "MSFT")
    d, c, v = slice_range(ph, "1y", today=date(2025, 6, 30))
    assert 240 <= len(d) <= 262
    d2, c2, v2, ds = downsample(*slice_range(ph, "max", today=date(2025, 6, 30)))
    assert ds is True and len(d2) <= 1501 and d2[-1] == ph.dates[-1]


def test_sec_ticker_map_and_symbols():
    profiles = [CompanyProfile("BRK.B", "Berkshire", "Financials", "x"), CompanyProfile("AAPL", "Apple", "IT", "y"),
                CompanyProfile("GOOG", "Alphabet C", "Comm", "z")]
    tmap = {"BRK-B": 1067983, "AAPL": 320193, "GOOGL": 1652044, "GOOG": 1652044}
    out = resolve_ciks(profiles, tmap)
    assert [p.cik for p in out] == [1067983, 320193, 1652044]
    assert yahoo_symbol("BRK.B") == "BRK-B" and stooq_symbol("BRK.B") == "brk-b.us"
    assert [p.ticker for p in search_companies(profiles, "berk")] == ["BRK.B"]
    assert search_companies(profiles, "goo")[0].ticker == "GOOG"


def test_max_filed():
    doc = {"facts": {"us-gaap": {"Assets": {"units": {"USD": [{"filed": "2024-11-01"}, {"filed": "2025-02-01"}]}}}}}
    assert max_filed(doc) == "2025-02-01"
