# GuFu — a GuruFocus-style stock research app for the S&P 500

GuFu computes valuation, profitability, financial-strength, growth and dividend metrics for every S&P 500
company from **real SEC filings** and **live market prices**, and presents them the way GuruFocus does:

- **Overview page** — market stat tiles, market cap by sector, top gainers/losers, lowest P/E, highest ROE,
  largest DCF discount, highest Piotroski F-score, plus a search bar over all constituents.
- **Company page** — live price and 52-week range, GuruFocus-style **rank badges** (Financial Strength,
  Profitability, Growth, Valuation, 1–10 against the S&P 500), an interactive price chart (1M → MAX), ~60
  metrics in colour-coded tables (P/E, PEG, P/S, P/B, P/FCF, EV/EBITDA, ROE, ROA, ROIC, margins, leverage,
  coverage, 1/3/5/10-year growth rates, yields, payout), Altman Z and Piotroski F badges with the underlying
  tests, a 30-year financials chart, and an interactive two-stage DCF panel.
- **30-Y Financials tab** — five GuruFocus-style tables (Per Share Data, Ratios, Income Statement, Balance
  Sheet, Cashflow Statement): 30 fiscal years fitted to your screen width, then TTM and the last five
  quarters, a trend sparkline per row, $ / YoY % view, historical P/E, P/S, P/B and yield at each year-end,
  CSV export. Years from 2009 on come from SEC XBRL data; earlier years are parsed from the company's older
  10-K filings (see below), shown in italics and linked to the filing.
- **Valuation, Dividend and Peers tabs** — historical valuation multiples with a chart, the DCF model,
  dividend history with growth/payout/yield, and a comparison table of the largest companies in the same
  industry.
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

**30 years of history.** SEC structured (XBRL) data only exists for fiscal years ending 2009 or later.
For earlier years GuFu goes back to the company's own older 10-K filings on EDGAR and parses two things:
the five-year **"Selected Financial Data"** table (revenue, operating income, net income, EPS, dividends,
total assets, long-term debt, equity, often cash flow) and the **primary statements** (income statement
and cash flow for three years, balance sheet for two). It fetches roughly one 10-K every three years
(FY2008, 2005, 2002, 1999, 1996 for a typical company), so income and cash-flow lines are continuous back
to the mid-1990s and balance-sheet detail is complete for two of every three years, with the key
balance-sheet figures filled from the summary tables. Parsed values are shown in italics with a "10-K"
tag, every one links to the filing it came from, restatements in later filings win, and a
"Re-extract older years" button re-runs the parser. The parser is rule-based and old filings vary, so
expect an occasional missing or mislabeled figure; the "notes from parsing" list on the tab says what
was dropped and why.

## Just open it (nothing to install)

The easiest way for anyone, on any device, is the **hosted edition**: a static website rebuilt every night
from SEC filings and closing prices and published on GitHub Pages. Once the nightly workflow has run
(see *Publishing* below) it lives at **https://goatercoder.github.io/GuFu/**. Open the link, type a
company name, done. It never sleeps, loads instantly, and on a phone or tablet you can add it to the home
screen like an app (Share → *Add to Home Screen* on iPhone, the ⋮ menu → *Install app* on Android/Chrome).
Prices on the hosted edition are the previous close; everything else is identical.

### Publishing the hosted edition (repo owner, one-time)
1. Repo **Settings → Pages → Source: GitHub Actions**.
2. **Settings → Secrets and variables → Actions → New repository secret**: `GUFU_SEC_USER_AGENT` =
   `GuFu nightly build your@email` (the SEC requires a contact on every request).
3. **Actions → "Nightly data build & Pages deploy" → Run workflow**. The first run takes 30–60 minutes
   (every S&P 500 company's XBRL data, older 10-Ks and price history); later runs reuse the previous
   night's cache. It also publishes the cache as the `data-latest` release asset, which every other way of
   running GuFu downloads on first start so nobody has to wait for a build again.

## Run it on your own computer

Only Python 3.11+ is needed. On first start it downloads the nightly dataset (~30 MB) when one has been
published, so the app is fully populated within seconds; otherwise it builds the cache itself. Nothing to configure: the first time you open the app it asks for your name and
email (the SEC requires a contact on every request to its filing database) and then builds its data cache.

**macOS**
1. Install Python from <https://www.python.org/downloads/> if you don't have it.
2. Download this repo (green **Code** button → **Download ZIP**) and unzip it, or `git clone` it.
3. Double-click **`start.command`**. If macOS says it can't be opened, right-click it → **Open** (first time only).

**Windows**
1. Install Python from <https://www.python.org/downloads/windows/> and tick **"Add python.exe to PATH"**.
2. Download ZIP and unzip it, or `git clone`.
3. Double-click **`start.bat`**.

**Linux**: `./start.sh` (or `make start`).

Your browser opens at <http://127.0.0.1:8000>. The first run installs dependencies (about a minute). Keep the
window open while you use GuFu; close it to stop. If no nightly dataset is available yet, the S&P 500 cache
builds in the background (progress bar on the overview page) and company pages work immediately.

**Docker**: `docker compose up` then open <http://localhost:8000>. Data persists in the `gufu-data` volume.

**Web link (hosted)**: [![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/goatercoder/GuFu)
gives you a public URL on Render's free tier. Render asks for `GUFU_SEC_USER_AGENT` at deploy time
(format `GuFu/0.1 (Your Name; you@example.com)`); leave it blank and the app asks in the browser instead.
Free-tier caveats: the service sleeps after 15 minutes idle and its disk is wiped on every deploy or restart, so
the cache rebuilds afterwards; company pages still work immediately. The URL is public, so anyone with it can
use the app and its `/api/admin` endpoints. A paid instance with a persistent disk at `/app/backend/data` keeps
the cache.

### On a Chromebook

Chromebooks can't run the double-click launchers or Docker, so use one of these instead:

1. **Web link, nothing to install** — click
   [![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/goatercoder/GuFu),
   sign in with GitHub, click **Deploy**, then open the URL Render shows you. Enter your name and email on
   the welcome screen. (Free tier: sleeps when idle, cache rebuilds after restarts, URL is public.)
2. **GitHub Codespaces, private and in the browser** — click
   [![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/goatercoder/GuFu?quickstart=1).
   A browser-based editor starts, installs GuFu, launches it, and opens the app in a new tab (if the tab is
   blocked, click the **Ports** tab at the bottom and open port 8000). Only your GitHub account can open that
   URL. Data persists as long as the codespace exists; free accounts get 60 core-hours a month, and idle
   codespaces stop automatically (reopen the same codespace from github.com/codespaces to resume).
3. **Linux on ChromeOS** — Settings → About ChromeOS → Developers → Linux development environment → **Turn on**.
   Then in the Terminal app:
   ```bash
   git clone https://github.com/goatercoder/GuFu && cd GuFu && ./start.sh
   ```
   Chrome opens <http://localhost:8000> (open it yourself if it doesn't). Next time: `cd GuFu && ./start.sh`.

### Offline / sample mode

```bash
GUFU_FIXTURE_MODE=1 make start      # or: make dev-fixture for the two-server dev setup
```

Runs the full app with **no network** on deterministic synthetic data shaped exactly like the SEC and
Yahoo responses (the header shows a red *SAMPLE DATA MODE* badge). This is what the automated tests use;
it is not real market data.

## For developers

```bash
make setup      # python venv + pip install, npm install (needs Node 22+)
make dev        # backend on :8000 with reload, Vite dev server on :5173
make build      # rebuild frontend/dist  (commit it: end users run the built UI without Node)
make test       # pytest
make lint       # ruff + tsc
make e2e        # Playwright: fixture-mode smoke test + the first-run setup flow
```

`GUFU_SEC_USER_AGENT` can also be set in `.env` or the environment; that skips the setup screen. Facts are
refreshed weekly (only re-parsed when a newer filing appears), prices daily. `make refresh` forces a rebuild.

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
| `GET /api/company/{ticker}/financials?freq=annual\|quarterly` | period rows from 10-K / 10-Q with source tags, derivation flags, `legacy` markers with filing links, and 30-year coverage |
| `GET /api/company/{ticker}/prices?range=1m…max` | daily closes (downsampled for long ranges) |
| `GET /api/company/{ticker}/quote` | live quote |
| `GET /api/screener?sector=&pe_max=&roe_min=&sort=&order=&page=&columns=` | screener (`{metric}_min` / `{metric}_max` for any screenable metric; percent metrics in whole percent) |
| `GET /api/screener/facets`, `GET /api/metrics/definitions` | filter options and metric metadata |
| `GET /api/home` | overview page data |
| `POST /api/company/{ticker}/legacy/refresh` | re-fetch and re-parse the older 10-K filings for one company |
| `POST /api/admin/refresh?kind=all\|facts\|legacy\|prices\|metrics&force=` / `GET /api/admin/jobs/latest` | trigger / inspect builds |

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
