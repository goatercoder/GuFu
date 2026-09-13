#!/usr/bin/env python3
"""Rebuild data/sp500.json from Wikipedia's "List of S&P 500 companies" table.

Usage: python scripts/refresh_sp500.py [--out data/sp500.json]
Requires network access to en.wikipedia.org. Keeps CIKs from the table (used to skip the SEC ticker lookup).
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_table = False
        self.rows: list[list[str]] = []
        self.row: list[str] | None = None
        self.cell: list[str] | None = None
        self.depth = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table" and a.get("id") == "constituents":
            self.in_table = True
        if not self.in_table:
            return
        if tag == "tr":
            self.row = []
        elif tag in ("td", "th"):
            self.cell = []

    def handle_endtag(self, tag):
        if not self.in_table:
            return
        if tag in ("td", "th") and self.cell is not None and self.row is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if self.row:
                self.rows.append(self.row)
            self.row = None
        elif tag == "table":
            self.in_table = False

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "data" / "sp500.json"))
    args = ap.parse_args()
    req = urllib.request.Request(URL, headers={"User-Agent": "GuFu sp500 refresh (github.com/goatercoder/GuFu)"})
    html = urllib.request.urlopen(req, timeout=60).read().decode("utf-8")
    p = TableParser()
    p.feed(html)
    if not p.rows:
        print("constituents table not found", file=sys.stderr)
        return 1
    header = [h.lower() for h in p.rows[0]]
    idx = {name: header.index(col) for name, col in (("ticker", "symbol"), ("name", "security"), ("sector", "gics sector"),
                                                      ("sub", "gics sub-industry"), ("cik", "cik"))}
    out = []
    for r in p.rows[1:]:
        if len(r) <= max(idx.values()):
            continue
        cik = r[idx["cik"]].strip()
        out.append({"ticker": r[idx["ticker"]].strip().upper(), "name": r[idx["name"]].strip(), "sector": r[idx["sector"]].strip(),
                    "sub_industry": r[idx["sub"]].strip(), "cik": int(cik) if cik.isdigit() else None})
    out.sort(key=lambda x: x["ticker"])
    Path(args.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"wrote {len(out)} companies to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
