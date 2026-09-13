"""Locate and extract financial tables from an old 10-K document.

Two layers per document:
  * the "Selected Financial Data" five-year summary (key figures, regular format)   -> method "summary"
  * the primary statements (income 3y, balance 2y, cash flow 3y), best effort with
    consistency checks                                                             -> methods "income" / "balance" / "cashflow"
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from gufu.legacy import labels as L
from gufu.legacy.tables import Document, Table, document_scale, parse_document

SECTION_RE = {
    "summary": re.compile(
        r"selected\s+(consolidated\s+)?(five[-\s]year\s+)?financial\s+(data|information|summary)"
        r"|(five|six|ten|eleven)[-\s]year\s+(financial\s+)?(summary|review|selected|data|highlights)"
        r"|financial\s+highlights|item\s+6\b",
        re.I,
    ),
    "income": re.compile(
        r"(consolidated\s+)?statements?\s+of\s+(consolidated\s+)?(income|operations|earnings)\b|consolidated\s+income\s+statements?", re.I
    ),
    "balance": re.compile(r"(consolidated\s+)?balance\s+sheets?|statements?\s+of\s+financial\s+(position|condition)", re.I),
    "cashflow": re.compile(r"(consolidated\s+)?statements?\s+of\s+cash\s+flows?", re.I),
}
ALLOWED = {"summary": L.SUMMARY_FIELDS, "income": L.INCOME_FIELDS, "balance": L.BALANCE_FIELDS, "cashflow": L.CASHFLOW_FIELDS}
WINDOW = {"summary": 60_000, "income": 30_000, "balance": 30_000, "cashflow": 30_000}
MIN_FIELDS = {"summary": 3, "income": 3, "balance": 3, "cashflow": 2}
ABS_FIELDS = {"capex", "dividends_paid", "buybacks", "dna"}
YEAR_MIN, YEAR_MAX = 1985, 2015


@dataclass
class Extraction:
    years: dict[int, dict[str, float]] = field(default_factory=dict)
    methods: dict[int, dict[str, str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    sections: dict[str, bool] = field(default_factory=dict)

    def put(self, fy: int, fld: str, val: float, method: str) -> None:
        self.years.setdefault(fy, {})
        self.methods.setdefault(fy, {})
        if fld not in self.years[fy]:
            self.years[fy][fld] = val
            self.methods[fy][fld] = method

    def merge_from(self, other: Extraction) -> None:
        for fy, vals in other.years.items():
            for fld, v in vals.items():
                self.put(fy, fld, v, other.methods[fy][fld])
        self.warnings.extend(w for w in other.warnings if w not in self.warnings)
        for k, v in other.sections.items():
            self.sections[k] = self.sections.get(k, False) or v


# --------------------------------------------------------------------------------------------
# single table
# --------------------------------------------------------------------------------------------

_SHARES_CTX = re.compile(r"shares|weighted", re.I)
_EPS_CTX = re.compile(r"per\s+(common\s+)?share|earnings\s+per|income\s+per", re.I)


def _map_row_label(label: str, context: str, allowed: set[str]) -> str | None:
    lab = L.normalise_label(label)
    if lab in ("diluted", "basic", "assuming dilution", "fully diluted", "primary") and context:
        if _SHARES_CTX.search(context) and not _EPS_CTX.search(context):
            return "shares_diluted" if lab != "basic" and lab != "primary" else "shares_basic"
        if _EPS_CTX.search(context):
            return "eps_diluted" if lab != "basic" and lab != "primary" else "eps_basic"
    if context and lab and not L.PER_SHARE_RE.search(lab) and _EPS_CTX.search(context) and lab in ("net income", "net earnings", "income", "earnings", "net income (loss)"):
        return "eps_diluted"  # "Per share: Net income" style
    return L.map_label(label, allowed)


def extract_table(table: Table, kind: str, years: list[int] | None = None, scale: float | None = None) -> Extraction:
    out = Extraction()
    years = years or table.years
    if len(years) < 2:
        return out
    scale = scale or table.scale or 1.0
    allowed = ALLOWED[kind]
    context = ""
    for row in table.rows:
        if not row.tokens:
            context = row.label
            continue
        fld = _map_row_label(row.label, context, allowed)
        if fld is None:
            continue
        vals = row.values
        # drop footnote markers like "(1)" that leaked into the token list
        if len(vals) > len(years):
            vals = [v for v, t in zip(vals, row.tokens, strict=True) if not re.fullmatch(r"\(\s*\d\s*\)", t.strip())]
        if len(vals) > len(years):
            vals = [v for v, t in zip(vals, [t for t in row.tokens if not re.fullmatch(r"\(\s*\d\s*\)", t.strip())], strict=True) if not t.strip().endswith("%")]
        if len(vals) != len(years):
            continue
        mult = 1.0 if fld in L.PER_SHARE_FIELDS else scale
        for fy, v in zip(years, vals, strict=True):
            if v is None or not (YEAR_MIN <= fy <= YEAR_MAX):
                continue
            val = v * mult
            if fld in ABS_FIELDS:
                val = abs(val)
            if fld in L.PER_SHARE_FIELDS and abs(val) > 5000:
                continue
            out.put(fy, fld, val, kind)
    return out


# --------------------------------------------------------------------------------------------
# document
# --------------------------------------------------------------------------------------------


def _tables_in_window(doc: Document, pos: int, window: int) -> list[Table]:
    return [t for t in doc.tables if pos <= t.offset <= pos + window]


def _score(ex: Extraction) -> int:
    return sum(len(v) for v in ex.years.values())


def _extract_section(doc: Document, kind: str, doc_scale: float | None) -> Extraction:
    best = Extraction()
    best_score = 0
    seen_starts: set[int] = set()
    for m in SECTION_RE[kind].finditer(doc.text):
        pos = m.start()
        if any(abs(pos - s) < 200 for s in seen_starts):
            continue
        seen_starts.add(pos)
        cand = Extraction()
        current_years: list[int] = []
        current_scale: float | None = None
        tables_used = 0
        for t in _tables_in_window(doc, pos, WINDOW[kind]):
            years = t.years
            scale = t.scale if t.scale_source else (doc_scale or t.scale)
            if years:
                current_years, current_scale = years, scale
            elif current_years and doc.kind == "text":
                years, scale = current_years, current_scale or scale  # continuation of a page-split text table
            else:
                continue
            ex = extract_table(t, kind, years, scale)
            n = _score(ex)
            if n == 0:
                continue
            if kind != "summary" and tables_used >= 1 and n < MIN_FIELDS[kind]:
                continue  # after the statement itself, ignore note tables with a stray matching label
            cand.merge_from(ex)
            tables_used += 1
            if kind != "summary" and tables_used >= 2:
                break
            if kind == "summary" and tables_used >= 6:
                break
        sc = _score(cand)
        if sc > best_score:
            best, best_score = cand, sc
        if best_score >= 40:
            break
    best.sections[kind] = best_score >= MIN_FIELDS[kind]
    if not best.sections[kind]:
        return Extraction(sections={kind: False})
    return best


def _check_consistency(ex: Extraction) -> None:
    for fy, v in list(ex.years.items()):
        m = ex.methods[fy]
        ta, le = v.get("total_assets"), v.get("liabilities_and_equity")
        if ta is not None and le is not None and ta > 0 and abs(ta - le) / ta > 0.02:
            ex.warnings.append(f"FY{fy}: balance sheet does not balance (assets {ta:.0f} vs L+E {le:.0f}); balance-sheet items dropped")
            for k in [k for k, meth in m.items() if meth == "balance"]:
                v.pop(k, None)
                m.pop(k, None)
        rev, cogs, gp = v.get("revenue"), v.get("cost_of_revenue"), v.get("gross_profit")
        if rev is not None and rev <= 0 and m.get("revenue") != "summary":
            ex.warnings.append(f"FY{fy}: non-positive revenue dropped")
            v.pop("revenue", None)
            m.pop("revenue", None)
        if rev and cogs is not None and gp is not None and abs((rev - cogs) - gp) / max(abs(rev), 1) > 0.02:
            ex.warnings.append(f"FY{fy}: gross profit inconsistent with revenue − cost of sales; gross profit dropped")
            v.pop("gross_profit", None)
            m.pop("gross_profit", None)
        ni = v.get("net_income")
        if rev and ni is not None and abs(ni) > abs(rev) * 3:
            ex.warnings.append(f"FY{fy}: net income implausible vs revenue; dropped")
            v.pop("net_income", None)
            m.pop("net_income", None)
        # fallbacks
        if "net_income" not in v and "net_income_cont" in v:
            v["net_income"] = v["net_income_cont"]
            m["net_income"] = m["net_income_cont"] + " (continuing ops)"
        if "eps_diluted" not in v and "eps_basic" in v:
            v["eps_diluted"] = v["eps_basic"]
            m["eps_diluted"] = m["eps_basic"] + " (basic)"
        if "shares_diluted" not in v and "shares_basic" in v:
            v["shares_diluted"] = v["shares_basic"]
            m["shares_diluted"] = m["shares_basic"] + " (basic)"
        if "long_term_debt" not in v and "total_debt_reported" in v:
            pass  # total_debt_reported is used directly by _add_derived
        for k in ("net_income_cont", "eps_basic", "shares_basic", "liabilities_and_equity"):
            if k in v and k != "liabilities_and_equity":
                v.pop(k, None)
                m.pop(k, None)
        if not v:
            ex.years.pop(fy, None)
            ex.methods.pop(fy, None)


def extract_document(body: str) -> Extraction:
    """Extract everything we can from one document (primary 10-K or an EX-13 annual report)."""
    doc = parse_document(body)
    doc_scale = document_scale(doc.text)
    result = Extraction()
    # statements first (primary source), then the summary fills the remaining years/fields
    for kind in ("income", "balance", "cashflow", "summary"):
        ex = _extract_section(doc, kind, doc_scale)
        result.merge_from(ex)
    _check_consistency(result)
    return result


def extract_filing(documents: list[str]) -> Extraction:
    """Merge extractions from the documents of one filing (primary document + EX-13 exhibits)."""
    total = Extraction()
    for body in documents:
        try:
            ex = extract_document(body)
        except Exception as exc:  # noqa: BLE001
            total.warnings.append(f"document could not be parsed: {exc}")
            continue
        total.merge_from(ex)
    return total
