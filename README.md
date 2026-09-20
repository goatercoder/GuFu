<h1 align="center">GuFu</h1>

<p align="center">
  Fundamental-analysis platform for the S&amp;P 500, computed end-to-end from primary SEC filings and market prices.
</p>

<p align="center">
  <a href="https://github.com/goatercoder/GuFu/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/goatercoder/GuFu/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://github.com/goatercoder/GuFu/actions/workflows/data.yml"><img alt="Nightly data build" src="https://github.com/goatercoder/GuFu/actions/workflows/data.yml/badge.svg"></a>
  <img alt="Python" src="https://img.shields.io/badge/python-3.11%2B-blue">
  <img alt="Stack" src="https://img.shields.io/badge/stack-FastAPI%20%C2%B7%20React%2019%20%C2%B7%20TypeScript-informational">
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/license-source--available-lightgrey"></a>
</p>

---

## Overview

GuFu ingests every S&P 500 constituent's structured XBRL disclosures from SEC EDGAR, normalises them into consistent annual, quarterly and trailing-twelve-month series, extends the history back to the mid-1990s by parsing pre-XBRL 10-K filings, and derives roughly sixty valuation, profitability, financial-strength, growth and dividend metrics. The result is presented in a GuruFocus-style interface: an index overview, deep company pages with thirty-year statement tables, interactive valuation and DCF models, peer comparison and a full-index screener.

Every figure is computed by GuFu's own engine (`backend/gufu/metrics/`) from raw filing facts. No data is scraped from third-party research sites and no API keys are required.

## Features

- **Overview** — market statistics, capitalisation by sector, top movers, and ranked lists (lowest P/E, highest ROE, largest DCF discount, highest Piotroski F-score) with search across all constituents.
- **Company page** — live quote and 52-week range; rank badges for Financial Strength, Profitability, Growth and Valuation (1–10, relative to the index); price chart from 1M to MAX; colour-coded metric tables (P/E, PEG, P/S, P/B, P/FCF, EV/EBITDA, ROE, ROA, ROIC, margins, leverage, coverage, 1/3/5/10-year growth rates, yields, payout); Altman Z and Piotroski F with the underlying tests; a thirty-year financials chart and an interactive two-stage DCF.
- **30-Y Financials** — five statement tables (Per Share Data, Ratios, Income Statement, Balance Sheet, Cash Flow) fitted to the viewport: thirty fiscal years, TTM and the last five quarters, per-row trend sparklines, absolute / YoY toggle, year-end P/E, P/S, P/B and yield, CSV export. Pre-2009 values are rendered in italics and link to the originating filing.
- **Valuation, Dividend, Peers** — historical multiples with charting, the DCF model, dividend history with growth, payout and yield, and a same-industry comparison table.
- **Screener** — filter the entire index on any screenable metric (sector, market cap, P/E, PEG, P/B, yield, ROE, ROIC, growth, F/Z-score, margin of safety, …), sort on any column, choose columns.

## Data pipeline

| Data | Source | Processing |
|---|---|---|
| Financial statements | [SEC EDGAR XBRL `companyfacts`](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | ~40 canonical line items mapped across tag variants; restatements deduplicated (latest filing wins); discrete quarters derived from year-to-date cash-flow figures; TTM assembled from the last four quarters. |
| Pre-2009 history | Older 10-K filings on EDGAR | Rule-based parser for the five-year *Selected Financial Data* table and the primary statements; roughly one filing every three fiscal years gives continuous income and cash-flow series and two-of-three balance-sheet coverage. Every parsed value links to its filing; parser notes list anything dropped. |
| Ticker → CIK | `sec.gov/files/company_tickers.json` | |
| Index membership | `data/sp500.json` (bundled) | `make sp500` refreshes from Wikipedia. |
| Prices and quotes | Yahoo Finance chart endpoint, Stooq fallback | Daily closes back to listing; live quotes cached for 60 s. |

**Nightly build.** A scheduled GitHub Actions workflow rebuilds the complete dataset (XBRL facts, legacy filings, prices, metrics), publishes a slim SQLite snapshot as the `data-latest` release asset, and exports a static edition of the site. Every other deployment mode downloads that snapshot on first start, so a fresh instance is fully populated within seconds instead of spending 30–60 minutes talking to EDGAR.

## Getting started

### Hosted edition (nothing to install)

The static edition is published to GitHub Pages by the nightly workflow at **https://goatercoder.github.io/GuFu/**. It never sleeps, loads instantly, and installs to a phone home screen as a PWA. Prices are the previous close; everything else is identical to the full app.

Repository owners enable it once: **Settings → Pages → Source: GitHub Actions**, then run **Actions → Nightly data build & Pages deploy**.

### Local

Only Python 3.11+ is required. The first start downloads the nightly dataset (~30 MB) when one is available; otherwise the cache builds in the background while company pages work immediately.

| Platform | Steps |
|---|---|
| macOS | Install Python from python.org, download or clone the repo, double-click `start.command` (right-click → Open the first time). |
| Windows | Install Python with *Add python.exe to PATH*, download or clone, double-click `start.bat`. |
| Linux | `./start.sh` or `make start`. |

The browser opens at <http://127.0.0.1:8000>. Dependencies install on first run.

### Docker

```bash
docker compose up
```

Serves on <http://localhost:8000>; data persists in the `gufu-data` volume.

### Render

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/goatercoder/GuFu)

One click provisions a public URL on the free tier. `GUFU_SEC_USER_AGENT` may be set at deploy time (format `GuFu/0.1 (Your Name; you@example.com)`); left blank, the app uses the built-in contact. Free-tier instances sleep when idle and lose their disk on restart; a paid instance with a persistent disk at `/app/backend/data` keeps the cache.

### GitHub Codespaces / ChromeOS

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/goatercoder/GuFu?quickstart=1)

The dev container installs and launches GuFu and forwards port 8000. On ChromeOS with the Linux environment enabled:

```bash
git clone https://github.com/goatercoder/GuFu && cd GuFu && ./start.sh
```

### Offline / fixture mode

```bash
GUFU_FIXTURE_MODE=1 make start      # or: make dev-fixture
```

Runs the full application against deterministic synthetic data shaped like the SEC and Yahoo responses, with no network access. The header displays a *SAMPLE DATA MODE* badge. This mode backs the automated tests; it is not market data.

## Architecture

```
backend/gufu/
  xbrl/        companyfacts → annual / quarterly / TTM rows (tags.py: tag fallback lists; normalize.py: pipeline)
  legacy/      pre-XBRL 10-K parser and merge logic
  metrics/     definitions.py (labels, thresholds, explanations), engine.py, growth.py, scores.py, dcf.py
  fetch/       SEC, Yahoo and Stooq clients; fixtures.py + synthetic.py for offline mode
  jobs/        background builder and scheduler (SQLite cache in backend/data/gufu.sqlite)
  services/    company bundle, quote cache, in-memory screener with ranks and peers
  api/         FastAPI routes
  dataset.py   slim export and download-at-startup of the nightly snapshot
frontend/src/  React 19 + Vite + TypeScript + Tailwind + Recharts; static-data mode with client-side screener
scripts/       build_dataset.py, export_static.py, make_fixture.py, refresh_sp500.py
data/          sp500.json
```

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | cache status, build progress |
| `GET /api/companies?q=` | search the universe |
| `GET /api/company/{ticker}` | quote, grouped and colour-coded metrics, scores, DCF, data status |
| `GET /api/company/{ticker}/financials?freq=annual\|quarterly` | period rows with source tags, derivation flags, legacy markers with filing links, coverage |
| `GET /api/company/{ticker}/prices?range=1m…max` | daily closes (downsampled for long ranges) |
| `GET /api/company/{ticker}/quote` | live quote |
| `GET /api/screener?sector=&pe_max=&roe_min=&sort=&order=&page=&columns=` | screener; `{metric}_min` / `{metric}_max` for any screenable metric |
| `GET /api/screener/facets`, `GET /api/metrics/definitions` | filter options and metric metadata |
| `GET /api/home` | overview page data |
| `POST /api/company/{ticker}/legacy/refresh` | re-fetch and re-parse the older 10-K filings for one company |
| `POST /api/admin/refresh?kind=all\|facts\|legacy\|prices\|metrics&force=`, `GET /api/admin/jobs/latest` | trigger and inspect builds |

Interactive documentation is served at <http://localhost:8000/docs>. With the frontend built (`make build`) the backend serves the application itself.

## Methodology

- **Periods** are classified from each fact's own start and end dates (quarter ≈ 90 days, fiscal year ≈ 365 days), never from the filing's `fy`/`fp` labels. Restated values from later filings win. 10-Q cash-flow items are year-to-date, so Q2 = H1 − Q1, Q3 = 9M − H1, Q4 = FY − 9M (hatched in the quarterly chart).
- **TTM** is the last four consecutive quarters, or the latest 10-K when it is the most recent period.
- **P/E** = price ÷ TTM diluted EPS. **PEG** = P/E ÷ five-year EBITDA CAGR (an EPS-growth variant is also shown). **EV** = market cap + total debt − cash and short-term investments. **ROIC** = operating income × (1 − tax rate) ÷ average (equity + debt − cash).
- **Altman Z** uses the original 1968 formulation and is flagged as not meaningful for financials. **Piotroski F** compares the last two fiscal years.
- **DCF** is a two-stage model: ten years at the capped historical growth rate, ten years at 4 %, discounted at 10 %, applied to TTM EPS or FCF per share and adjustable in the UI.

All formulas live in `backend/gufu/metrics/`; `definitions.py` holds the explanations surfaced as tooltips.

## Development

```bash
make setup      # python venv + pip install, npm install (Node 22+)
make dev        # backend on :8000 with reload, Vite dev server on :5173
make build      # production frontend into frontend/dist (committed so end users need no Node)
make test       # pytest: period logic, normaliser, metrics, scores, DCF, API, setup flow
make lint       # ruff + tsc
make e2e        # Playwright smoke tests against a fixture-mode backend
make dataset    # headless full-cache build → build/gufu-data.sqlite.gz
make static     # static edition (no backend) from build/gufu.sqlite
```

CI runs ruff, pytest and the frontend build on every push.

### Configuration

All settings are `GUFU_*` environment variables or entries in a root `.env` (see `.env.example`). Notable ones:

| Variable | Default | Purpose |
|---|---|---|
| `GUFU_SEC_USER_AGENT` | built-in preset | Contact string the SEC requires on every EDGAR request |
| `GUFU_FIXTURE_MODE` | `0` | Offline synthetic data |
| `GUFU_DATASET_URL` | `data-latest` release asset | Prebuilt snapshot downloaded on first start; empty disables |
| `GUFU_AUTO_BUILD_ON_START` | `1` | Build the whole cache in the background on first start |
| `GUFU_FACTS_MAX_AGE_DAYS` / `GUFU_PRICES_MAX_AGE_HOURS` | `7` / `24` | Refresh cadence |
| `GUFU_SEC_RPS`, `GUFU_SEC_CONCURRENCY`, `GUFU_YAHOO_CONCURRENCY` | `8`, `6`, `3` | Rate limiting |

## Limitations

- Coverage is limited to S&P 500 constituents; any SEC filer can be added to `data/sp500.json`.
- Yahoo's chart endpoint is unofficial and occasionally rate-limits; GuFu retries, rotates hosts and falls back to Stooq. Quotes are delayed per Yahoo's feed.
- Banks and insurers do not report cost of revenue, inventory or current assets; affected ratios show N/A.
- The legacy 10-K parser is rule-based; old filings vary, so an occasional missing or mislabelled figure is expected and documented in the tab's parser notes.
- Nothing here is investment advice.

## License

Source-available, **all rights reserved**. The code may be read here and the hosted site used for personal, non-commercial purposes; copying, modifying, redistributing, hosting a copy, or any commercial use requires the author's written permission. See [LICENSE](LICENSE).
