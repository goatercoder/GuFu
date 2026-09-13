#!/usr/bin/env python3
"""Export the cache as static JSON so the frontend can run with no backend at all (GitHub Pages).

Usage: python scripts/export_static.py --db build/gufu.sqlite --out frontend/dist/data
Produces: companies.json, home.json, screener.json, facets.json, definitions.json,
          company/<T>.json, financials/<T>.json, prices/<T>.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

import orjson  # noqa: E402

from gufu.config import Settings  # noqa: E402
from gufu.jobs.builder import quote_from_history  # noqa: E402
from gufu.main import build_state  # noqa: E402
from gufu.metrics.definitions import METRIC_DEFS  # noqa: E402
from gufu.metrics.engine import compute_metrics, grouped_metrics  # noqa: E402
from gufu.prices import PriceHistory, close_on_or_before, downsample, slice_range  # noqa: E402
from gufu.services.company_service import attach_legacy, legacy_period_source, legacy_summary  # noqa: E402
from gufu.services.screener_service import SCREENABLE, compute_ranks, facets, flatten, home_summary, peers  # noqa: E402
from gufu.store.repo import now_iso  # noqa: E402
from gufu.xbrl.models import Financials  # noqa: E402
from gufu.xbrl.tags import CHART_FIELDS, field_kind, field_label, field_unit  # noqa: E402

RANGES = ["1m", "3m", "6m", "ytd", "1y", "2y", "5y", "10y", "max"]


def dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(orjson.dumps(obj))


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    settings = Settings(db_path=Path(a.db).resolve(), auto_build_on_start=False, dataset_url="", sec_user_agent="static export")
    state = build_state(settings)
    repo = state.repo
    rows = state.screener_rows
    built_at = now_iso()

    have = {r["ticker"] for r in rows}
    dump(out / "companies.json", [{"ticker": p.ticker, "name": p.name, "sector": p.sector, "sub_industry": p.sub_industry, "has_data": p.ticker in have} for p in state.profiles])
    dump(out / "definitions.json", [d.to_dict() for d in METRIC_DEFS])
    f = facets(rows)
    f["default_columns"] = [k for k in SCREENABLE if k in ("market_cap", "pe", "peg", "pb", "dividend_yield", "roe")]
    dump(out / "facets.json", f)
    dump(out / "screener.json", {"as_of": state.screener_built_at, "universe": len(state.profiles), "rows": rows, "fixture_mode": state.fetchers.fixture})
    dump(out / "home.json", home_summary(state, len(state.profiles)))

    n = 0
    for p in state.profiles:
        if not p.cik:
            continue
        fin_d = repo.get_financials(p.cik)
        if not fin_d:
            continue
        fin = Financials.from_dict(fin_d)
        attach_legacy(state, fin, p.cik)
        pr = repo.get_prices(p.ticker)
        ph = PriceHistory.from_dict(pr[0]) if pr else None
        quote = quote_from_history(ph) if ph else None
        if quote is None:
            from gufu.metrics.engine import Quote
            quote = Quote(price=None, stale=True)
        quote.stale = True  # prices are as of the nightly build
        res = compute_metrics(fin, quote, p.sector)
        profile = {"ticker": p.ticker, "name": p.name, "sector": p.sector, "sub_industry": p.sub_industry, "cik": p.cik}
        me = flatten({**profile, "values": res["values"], "quote": quote.to_dict()})
        bundle = {
            "profile": profile, "quote": quote.to_dict(), "metrics": res["values"], "groups": grouped_metrics(res["values"]),
            "ranks": compute_ranks(rows, p.ticker, me), "peers": peers(rows, p.ticker, p.sector, p.sub_industry),
            "scores": res["scores"], "dcf": res["dcf"], "inputs": res["inputs"], "ttm": fin.ttm.to_dict() if fin.ttm else None,
            "data_status": {
                "latest_10k_filed": fin.latest_10k_filed.isoformat() if fin.latest_10k_filed else None,
                "latest_10q_filed": fin.latest_10q_filed.isoformat() if fin.latest_10q_filed else None,
                "fye_month": fin.fye_month, "annual_years": len(fin.annual), "quarters": len(fin.quarterly),
                "first_fiscal_year": fin.annual[0].fiscal_year if fin.annual else None,
                "last_fiscal_year": fin.annual[-1].fiscal_year if fin.annual else None,
                "warnings": fin.warnings, "entity_name": fin.entity_name, "fixture_mode": state.fetchers.fixture,
                "built_at": built_at,
            },
        }
        dump(out / "company" / f"{p.ticker}.json", bundle)

        fields = [{"key": k, "label": field_label(k), "kind": field_kind(k), "unit": field_unit(k)} for k in CHART_FIELDS]
        fin_out = {}
        for freq, rws in (("annual", fin.annual), ("quarterly", fin.quarterly)):
            periods = []
            for r in rws:
                d = r.to_dict()
                d["legacy"] = "legacy" in r.derived
                d["source"] = legacy_period_source(fin, r.fiscal_year) if d["legacy"] else None
                d["px"] = close_on_or_before(ph, r.end.isoformat()) if ph else None
                d["v"] = {k: (round(v, 4) if abs(v) < 1e4 else round(v)) for k, v in d["v"].items()}
                if freq == "quarterly":
                    d.pop("src", None)  # keep the static files small; tag names are available in server mode
                periods.append(d)
            fin_out[freq] = periods
        ttm_d = fin.ttm.to_dict() if fin.ttm else None
        if ttm_d and ph:
            ttm_d["px"] = ph.last_price
        dump(out / "financials" / f"{p.ticker}.json", {
            "ticker": p.ticker, "fye_month": fin.fye_month, "fields": fields, "annual": fin_out["annual"], "quarterly": fin_out["quarterly"],
            "ttm": ttm_d, "warnings": fin.warnings, "legacy_status": "ready" if fin.legacy is not None else "none", **legacy_summary(fin),
            "source": "SEC EDGAR: XBRL companyfacts (10-K / 10-Q, 2009+) and Selected Financial Data / statements parsed from older 10-K filings",
            "coverage_note": "Fiscal years ending 2009 or later come from structured XBRL data. Earlier years are parsed from the company's older 10-K filings; each such value links to its filing and may need checking.",
        })
        if ph:
            ranges = {}
            for rng in RANGES:
                d, c, v = slice_range(ph, rng, today=date.today())
                d, c, v, ds = downsample(d, c, v, max_points=600 if rng in ("5y", "10y", "max") else 1500)
                ranges[rng] = {"downsampled": ds, "points": [{"d": dd, "c": cc, "v": vv} for dd, cc, vv in zip(d, c, v, strict=True)]}
            dump(out / "prices" / f"{p.ticker}.json", {"ticker": p.ticker, "symbol": ph.symbol, "currency": ph.currency, "meta": ph.meta,
                                                     "first_date": ph.dates[0] if ph.dates else None, "source": "Yahoo Finance (daily close, nightly build)", "ranges": ranges})
        n += 1
    dump(out / "meta.json", {"built_at": built_at, "companies": n, "fixture_mode": state.fetchers.fixture})
    total = sum(f.stat().st_size for f in out.rglob("*.json"))
    print(f"exported {n} companies to {out} ({total / 1e6:.1f} MB of JSON)")
    state.db.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
