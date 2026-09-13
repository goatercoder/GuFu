#!/usr/bin/env python3
"""Trim a real SEC companyfacts JSON into a small fixture (only the tags GuFu uses, last N fiscal years).

Usage: python scripts/make_fixture.py AAPL [--cik 320193] [--years 6]
Writes backend/fixtures/companyfacts_<TICKER>.json. Needs network access to data.sec.gov and GUFU_SEC_USER_AGENT.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from gufu.xbrl.tags import FIELD_SPECS  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker")
    ap.add_argument("--cik", type=int)
    ap.add_argument("--years", type=int, default=6)
    a = ap.parse_args()
    ua = os.environ.get("GUFU_SEC_USER_AGENT")
    if not ua:
        print("set GUFU_SEC_USER_AGENT", file=sys.stderr)
        return 1
    cik = a.cik
    if cik is None:
        req = urllib.request.Request("https://www.sec.gov/files/company_tickers.json", headers={"User-Agent": ua})
        rows = json.loads(urllib.request.urlopen(req, timeout=60).read())
        for r in rows.values():
            if r["ticker"].upper() == a.ticker.upper().replace(".", "-"):
                cik = int(r["cik_str"])
                break
    if cik is None:
        print("CIK not found", file=sys.stderr)
        return 1
    req = urllib.request.Request(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json", headers={"User-Agent": ua})
    doc = json.loads(urllib.request.urlopen(req, timeout=120).read())
    keep = {t.split(":")[-1] for s in FIELD_SPECS.values() for t in (*s.tags, *s.components)}
    min_year = max(int(f["fy"]) for tax in doc["facts"].values() for n in tax.values() for u in n["units"].values() for f in u if f.get("fy")) - a.years
    out = {"cik": doc["cik"], "entityName": doc["entityName"], "facts": {}}
    for tax, nodes in doc["facts"].items():
        for tag, node in nodes.items():
            if tag not in keep:
                continue
            units = {}
            for unit, series in node["units"].items():
                trimmed = [f for f in series if f.get("end", "0000") >= f"{min_year}-01-01" and f.get("form", "").startswith(("10-K", "10-Q"))]
                if trimmed:
                    units[unit] = trimmed
            if units:
                out["facts"].setdefault(tax, {})[tag] = {"label": node.get("label"), "description": "", "units": units}
    dest = ROOT / "backend" / "fixtures" / f"companyfacts_{a.ticker.upper()}.json"
    dest.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {dest} ({dest.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
