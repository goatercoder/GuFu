"""SEC EDGAR filing discovery for pre-XBRL 10-Ks, and document URL/SGML helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from gufu.xbrl import periods as P

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
SUBMISSIONS_PAGE_URL = "https://data.sec.gov/submissions/{name}"
ARCHIVE_BASE = "https://www.sec.gov/Archives/edgar/data/{cik}/{accn_nodash}"
TENK_FORMS = {"10-K", "10-K405", "10-KT", "10-KSB", "10-K/A", "10-K405/A", "10-KT/A"}
EARLIEST_FY = 1993


@dataclass(frozen=True)
class FilingRef:
    accn: str
    form: str
    filed: date
    report_date: date | None
    fiscal_year: int | None
    primary_doc: str

    @property
    def accn_nodash(self) -> str:
        return self.accn.replace("-", "")

    def base_url(self, cik: int) -> str:
        return ARCHIVE_BASE.format(cik=cik, accn_nodash=self.accn_nodash)

    def primary_url(self, cik: int) -> str:
        if self.primary_doc and not self.primary_doc.lower().endswith(".txt"):
            return f"{self.base_url(cik)}/{self.primary_doc}"
        return f"{self.base_url(cik)}.txt"  # full SGML submission (1990s filings)

    def index_url(self, cik: int) -> str:
        return f"{self.base_url(cik)}/{self.accn}-index.htm"

    def full_txt_url(self, cik: int) -> str:
        return f"{self.base_url(cik)}.txt"

    def human_url(self, cik: int) -> str:
        return self.index_url(cik)


def _columns(block: dict) -> list[dict]:
    keys = ["accessionNumber", "filingDate", "reportDate", "form", "primaryDocument"]
    cols = {k: block.get(k) or [] for k in keys}
    n = len(cols["accessionNumber"])
    return [{k: (cols[k][i] if i < len(cols[k]) else "") for k in keys} for i in range(n)]


def parse_submissions(main: dict, pages: list[dict] | None = None) -> list[dict]:
    rows = _columns(main.get("filings", {}).get("recent", {}))
    for pg in pages or []:
        rows.extend(_columns(pg))
    return rows


def page_names(main: dict) -> list[str]:
    return [f["name"] for f in main.get("filings", {}).get("files", []) if f.get("name")]


def tenk_filings(rows: list[dict], fye_month: int) -> list[FilingRef]:
    out: list[FilingRef] = []
    for r in rows:
        form = (r.get("form") or "").strip()
        if form not in TENK_FORMS:
            continue
        try:
            filed = date.fromisoformat(r["filingDate"][:10])
        except (KeyError, ValueError):
            continue
        rd = None
        try:
            rd = date.fromisoformat(r["reportDate"][:10]) if r.get("reportDate") else None
        except ValueError:
            rd = None
        fy = P.fiscal_year_for(P.period_key(rd), fye_month) if rd else None
        if fy is None:
            # no period-of-report: assume the fiscal year ended within the 4 months before filing
            approx = P.shift_months(filed, -3)
            fy = P.fiscal_year_for(P.period_key(approx), fye_month)
        out.append(FilingRef(r["accessionNumber"], form, filed, rd, fy, r.get("primaryDocument") or ""))
    return out


def select_filings(filings: list[FilingRef], first_xbrl_fy: int, max_filings: int = 6, step: int = 3) -> list[FilingRef]:
    """Pick 10-Ks so that 3-year statements cover every year and 5-year summaries overlap: FY X-1, X-4, X-7, ..."""
    by_fy: dict[int, list[FilingRef]] = {}
    for f in filings:
        if f.fiscal_year is None or f.fiscal_year >= first_xbrl_fy:
            continue
        by_fy.setdefault(f.fiscal_year, []).append(f)

    def best(fy: int) -> FilingRef | None:
        cands = by_fy.get(fy)
        if not cands:
            return None
        originals = [c for c in cands if not c.form.endswith("/A")]
        pool = originals or cands
        return max(pool, key=lambda c: c.filed)

    chosen: list[FilingRef] = []
    seen: set[str] = set()
    target = first_xbrl_fy - 1
    while target >= EARLIEST_FY and len(chosen) < max_filings:
        pick = best(target) or best(target - 1) or best(target + 1)
        if pick and pick.accn not in seen:
            chosen.append(pick)
            seen.add(pick.accn)
        target -= step
    return chosen


# --------------------------------------------------------------------------------------------
# documents
# --------------------------------------------------------------------------------------------

_DOC_RE = re.compile(r"<DOCUMENT>(.*?)</DOCUMENT>", re.S | re.I)
_TYPE_RE = re.compile(r"<TYPE>([^\s<]+)", re.I)
_TEXT_RE = re.compile(r"<TEXT>(.*?)(?:</TEXT>|$)", re.S | re.I)


def split_sgml(body: str) -> list[tuple[str, str]]:
    """Full-submission .txt -> [(type, text), ...]"""
    docs: list[tuple[str, str]] = []
    for m in _DOC_RE.finditer(body):
        block = m.group(1)
        t = _TYPE_RE.search(block)
        x = _TEXT_RE.search(block)
        if not x:
            continue
        docs.append(((t.group(1) if t else "").upper(), x.group(1)))
    if not docs and "<TEXT>" not in body.upper():
        docs.append(("10-K", body))
    return docs


def wanted_sgml_documents(docs: list[tuple[str, str]]) -> list[str]:
    """The main 10-K text plus any EX-13 annual-report exhibit, in that order."""
    main = [t for typ, t in docs if typ.startswith("10-K")]
    ex13 = [t for typ, t in docs if typ.startswith("EX-13")]
    return main[:1] + ex13[:3]


_INDEX_ROW_RE = re.compile(r'<a[^>]+href="([^"]+)"[^>]*>([^<]+)</a>\s*</td>\s*<td[^>]*>([^<]*)</td>', re.I | re.S)


def ex13_links(index_html: str, base_url: str) -> list[str]:
    """EX-13 document URLs from a filing's -index.htm page."""
    out: list[str] = []
    for href, _name, typ in _INDEX_ROW_RE.findall(index_html):
        if typ.strip().upper().startswith("EX-13"):
            url = href if href.startswith("http") else ("https://www.sec.gov" + href if href.startswith("/") else f"{base_url}/{href}")
            url = url.replace("/ix?doc=", "")
            if url not in out:
                out.append(url)
    return out[:3]
