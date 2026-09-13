Fixture-mode data (GUFU_FIXTURE_MODE=1).

Drop real captures here to replace the synthetic data for a ticker:

- `companyfacts_<TICKER>.json` — trimmed SEC companyfacts document (make one with `python scripts/make_fixture.py AAPL`)
- `yahoo_chart_<TICKER>.json` — a Yahoo `/v8/finance/chart/<SYM>?range=max&interval=1d` response
- `company_tickers.json` — SEC ticker → CIK map

Tickers without a file fall back to `gufu/fetch/synthetic.py`.
