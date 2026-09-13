# GuFu — a GuruFocus-style stock research app for the S&P 500

GuFu computes valuation, profitability, financial-strength, growth and dividend metrics for every S&P 500
company from **real SEC filings** and **live market prices**, and presents them the way GuruFocus does:

- **Overview page** — market stat tiles, market cap by sector, top gainers/losers, lowest P/E, highest ROE,
  largest DCF discount, highest Piotroski F-score, plus a search bar over all constituents.
- **Company page** — live price and 52-week range, an interactive price chart (1M → MAX), ~60 metrics in
  colour-coded tables (P/E, PEG, P/S, P/B, P/FCF, EV/EBITDA, ROE, ROA, ROIC, margins, leverage, coverage,
  1/3/5/10-year growth rates, yields, payout), Altman Z and Piotroski F badges with the underlying tests,
  a **30-year financials chart** (annual or quarterly, any line item, compare two items) built from the
  company's 10-K / 10-Q XBRL data, and an interactive two-stage DCF panel.
- **Screener** — filter the whole index on any screenable metric (sector, market cap, P/E, PEG, P/B,
  yield, ROE, ROIC, growth, F/Z-score, margin of safety…), sort by any column, pick your own columns.

Every metric is computed by GuFu's own code (`backend/gufu/metrics/`) from raw filing facts; nothing is
scraped from GuruFocus.

## Data sources (free, no API keys)

| Data | Source | Notes |
|---|---|---|
| Financial statements | [SEC EDGAR XBRL companyfacts API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | Every fact a company reported in its 10-K and 10-Q filings. GuFu maps ~40 canonical line items across tag variants, dedupes restatements, derives discrete quarters from year-to-date cash-flow figures, and builds TTM. |
| Ticker → CIK | `https://www.sec.gov/files/company_tickers.json` | |
| S&P 500 membership | `data/sp500.json` (bundled) | Refresh from Wikipedia with `make sp500`. |
| Prices / quotes | Yahoo Finance chart endpoint (unofficial) | Daily closes back to listing; live quote with a 60 s cache. Stooq CSV is the fallback. |

**Coverage caveat.** SEC structured (XBRL) data only exists for fiscal years ending 2009 or later. The
"30-year" chart therefore has a 30-year axis but plots the ~15–17 years that exist in machine-readable
filings; pre-2009 years are not available from 10-K/10-Q filings in structured form.

## Quick start

```bash
git clone https://github.com/goatercoder/GuFu && cd GuFu
make setup                     # python venv + pip install, npm install
cp .env.example .env           # then edit GUFU_SEC_USER_AGENT
make dev                       # backend on :8000, frontend on :5173
```

Open <http://localhost:5173>. The SEC **requires** a descriptive `User-Agent` on every request, so live mode
refuses to start until `GUFU_SEC_USER_AGENT="GuFu research app your-name your@email"` is set.

On first start the backend builds the whole S&P 500 cache in the background: ~505 companyfacts documents
(rate-limited to 8 req/s), ~505 price histories, then all metrics. Expect 10–20 minutes; the overview page
shows a progress bar and fills in as it goes. Company pages work immediately, fetching on demand. Facts are
refreshed weekly (only re-parsed when a newer filing appears), prices daily. `make refresh` forces a rebuild.

Requirements: Python 3.11+, Node 22+.

### Offline / sample mode

```bash
make dev-fixture      # GUFU_FIXTURE_MODE=1
```

Runs the full app with **no network** on deterministic synthetic data shaped exactly like the SEC and
Yahoo responses (the header shows a red *SAMPLE DATA MODE* badge). This is what the automated tests use;
it is not real market data.

## Project layout

```
backend/gufu/
  xbrl/        companyfacts → annual / quarterly / TTM rows (tags.py = tag fallback lists, normalize.py = pipeline)
  metrics/     definitions.py (labels, thresholds, explanations), engine.py, growth.py, scores.py, dcf.py
  fetch/       SEC, Yahoo, Stooq clients; fixtures.py + synthetic.py for offline mode
  jobs/        background builder + scheduler (SQLite cache in backend/data/gufu.sqlite)
  services/    company bundle, live quote cache, in-memory screener
  api/         FastAPI routes
frontend/src/  React + Vite + TypeScript + Tailwind + Recharts
data/sp500.json, scripts/refresh_sp500.py, scripts/make_fixture.py
```

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | cache status, build progress |
| `GET /api/companies?q=` | search the universe |
| `GET /api/company/{ticker}` | quote, all metrics (grouped + colour-coded), scores, DCF, data status |
| `GET /api/company/{ticker}/financials?freq=annual\|quarterly` | period rows from 10-K / 10-Q with source tags and derivation flags |
| `GET /api/company/{ticker}/prices?range=1m…max` | daily closes (downsampled for long ranges) |
| `GET /api/company/{ticker}/quote` | live quote |
| `GET /api/screener?sector=&pe_max=&roe_min=&sort=&order=&page=&columns=` | screener (`{metric}_min` / `{metric}_max` for any screenable metric; percent metrics in whole percent) |
| `GET /api/screener/facets`, `GET /api/metrics/definitions` | filter options and metric metadata |
| `GET /api/home` | overview page data |
| `POST /api/admin/refresh?kind=all\|facts\|prices\|metrics&force=` / `GET /api/admin/jobs/latest` | trigger / inspect builds |

Interactive docs at <http://localhost:8000/docs>. Building the frontend (`make build`) lets the backend
serve the app itself at <http://localhost:8000>.

## How the numbers are computed

- **Periods**: facts are classified by their own start/end dates (quarter ≈ 90 d, FY ≈ 365 d), never by
  the filing's `fy`/`fp` labels. Restated values from later filings win. Cash-flow items in 10-Qs are
  year-to-date, so Q2 = H1 − Q1, Q3 = 9M − H1, Q4 = FY − 9M (shown hatched in the quarterly chart).
- **TTM** = the last four consecutive quarters, or the latest 10-K when it is the most recent period.
- **P/E** = price ÷ TTM diluted EPS; **PEG** = P/E ÷ 5-year EBITDA CAGR (GuruFocus definition; an
  EPS-growth variant is also shown); **EV** = market cap + total debt − cash & short-term investments;
  **ROIC** = operating income × (1 − tax rate) ÷ average (equity + debt − cash); **Altman Z** uses the
  original 1968 formula (flagged as not meaningful for financials); **Piotroski F** compares the last two
  fiscal years; **DCF** is a two-stage model (10 years at the capped historical growth rate, then 10 years
  at 4 %, discounted at 10 %) on TTM EPS or FCF per share, adjustable in the UI.
- All formulas live in `backend/gufu/metrics/` with explanations in `definitions.py` (shown as tooltips).

## Tests

```bash
make test     # pytest: period logic, normaliser (restatements, tag switches, YTD → quarters, banks), metrics, scores, DCF, API
make lint     # ruff + tsc
make e2e      # Playwright smoke test against a fixture-mode backend (home, company, screener)
```

## Notes and limitations

- Only S&P 500 constituents are supported (extend `data/sp500.json` to add more; any SEC filer works).
- Yahoo's chart endpoint is unofficial and occasionally rate-limits; GuFu retries, swaps hosts and falls
  back to Stooq. Quotes are delayed per Yahoo's feed.
- Banks and insurers report no cost of revenue, inventory or current assets; the affected ratios show N/A.
- Nothing here is investment advice.
