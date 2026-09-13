"""Turn old 10-K documents (HTML or fixed-width text) into simple row grids.

Every table is reduced to the same shape:  a list of rows, each row = (label, [tokens]) where tokens are
the numeric-looking cells in reading order.  Year columns are recognised from the header rows, so a
value row with the same number of tokens as there are year columns maps one-to-one.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

YEAR_RE = re.compile(r"(?<!\d)((?:19[89]\d|20[0-2]\d))(?!\d)")
FISCAL_RE = re.compile(r"fiscal\s+(?:year\s+)?(\d{4})", re.I)
DATE_RE = re.compile(
    r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2},?\s+((?:19[89]\d|20[0-2]\d))", re.I
)
MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}

NUM_TOKEN_RE = re.compile(r"^\(?\$?\s*-?\(?[\d,]*\.?\d+\)?%?\)?$")
DASH_TOKENS = {"-", "--", "—", "–", "―", "n/a", "na", "nm", "n.m.", "*", "(a)", "(b)"}
SCALE_RE = re.compile(
    r"\(?(?:(?:dollars|amounts|figures)\s+)?in\s+(millions|thousands|billions)|\(\s*(000s?|\$000s?)\s*(?:omitted)?\s*\)|000'?s\s+omitted",
    re.I,
)


@dataclass
class Row:
    label: str
    tokens: list[str]
    raw: str = ""

    @property
    def values(self) -> list[float | None]:
        return [parse_number(t) for t in self.tokens]


@dataclass
class Table:
    rows: list[Row]
    preface: str = ""  # text immediately before the table (scale hints)
    offset: int = 0  # position in the flattened document text
    kind: str = "html"
    years: list[int] = field(default_factory=list)
    scale: float = 1.0
    scale_source: str = ""


@dataclass
class Document:
    text: str  # flattened text for heading search
    tables: list[Table]
    kind: str  # html | text


# --------------------------------------------------------------------------------------------
# numbers
# --------------------------------------------------------------------------------------------


def parse_number(tok: str) -> float | None:
    t = tok.strip().replace("$", "").replace(",", "").replace(" ", "").strip()
    if not t or t.lower() in DASH_TOKENS:
        return None
    neg = False
    if t.startswith("(") and t.endswith(")"):
        neg = True
        t = t[1:-1].strip()
    elif t.startswith("(") and not t.endswith(")"):
        neg = True
        t = t[1:].strip()
    elif t.endswith(")") and not t.startswith("("):
        neg = True
        t = t[:-1].strip()
    if t.endswith("%"):
        return None  # percentages are never one of our fields
    if t.startswith("-"):
        neg = not neg if t.count("-") % 2 else neg
        t = t.lstrip("-").strip()
    if not re.fullmatch(r"\d*\.?\d+", t):
        return None
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg else v


def is_numeric_token(tok: str) -> bool:
    t = tok.strip().replace(" ", " ").strip()
    if not t:
        return False
    if t.lower() in DASH_TOKENS:
        return True
    return bool(NUM_TOKEN_RE.match(t.replace(" ", "")))


def _clean(s: str) -> str:
    s = html.unescape(s).replace(" ", " ").replace("’", "'")
    return re.sub(r"\s+", " ", s).strip()


FOOTNOTE_RE = re.compile(r"\s*(\(\s*[a-z0-9]{1,2}\s*\)|\*+|\[\d\])+\s*$", re.I)


def clean_label(label: str) -> str:
    label = _clean(label)
    label = FOOTNOTE_RE.sub("", label)
    label = label.rstrip(":.").strip()
    return label


# --------------------------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------------------------


class _GridParser(HTMLParser):
    """Collects text and tables in document order."""

    BLOCK_TAGS = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table", "hr", "td", "th"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.tables: list[Table] = []
        self._stack: list[dict] = []  # nested tables
        self._skip = 0  # inside <script>/<style>
        self._pos = 0
        self._tail = ""  # last 800 chars emitted, cheap "text before this table"

    # text position bookkeeping ---------------------------------------------------------------
    def _emit(self, s: str) -> None:
        self.out.append(s)
        self._pos += len(s)
        self._tail = (self._tail + s)[-800:]

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
            return
        if tag == "table":
            self._stack.append({"rows": [], "row": None, "cell": None, "start": self._pos, "preface": self._tail})
            self._emit("\n")
            return
        if self._stack:
            t = self._stack[-1]
            if tag == "tr":
                t["row"] = []
            elif tag in ("td", "th"):
                t["cell"] = []
            elif tag == "br" and t.get("cell") is not None:
                t["cell"].append(" ")
        if tag in self.BLOCK_TAGS:
            self._emit("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
            return
        if not self._stack:
            if tag in self.BLOCK_TAGS:
                self._emit("\n")
            return
        t = self._stack[-1]
        if tag in ("td", "th") and t.get("cell") is not None:
            cell = _clean("".join(t["cell"]))
            if t.get("row") is None:
                t["row"] = []
            t["row"].append(cell)
            self._emit(" " + cell)
            t["cell"] = None
        elif tag == "tr" and t.get("row") is not None:
            t["rows"].append(t["row"])
            t["row"] = None
            self._emit("\n")
        elif tag == "table":
            done = self._stack.pop()
            if done.get("row"):
                done["rows"].append(done["row"])
            table = _rows_to_table(done["rows"], "html")
            table.offset = done["start"]
            table.preface = done["preface"]
            self.tables.append(table)
            self._emit("\n")

    def handle_data(self, data):
        if self._skip:
            return
        if self._stack and self._stack[-1].get("cell") is not None:
            self._stack[-1]["cell"].append(data)
        elif self._stack and self._stack[-1].get("row") is None:
            # text inside a table but outside cells (rare)
            self._emit(data)
        else:
            self._emit(data)


def _merge_currency_cells(cells: list[str]) -> list[str]:
    """Join the '$', ')' and '%' fragments that old filings put in their own cells."""
    out: list[str] = []
    for c in cells:
        cs = c.strip()
        if cs in (")", "%", ")%"):
            if out:
                out[-1] = out[-1] + cs
            continue
        if cs == "$" or cs == "($":
            out.append(cs)  # placeholder, merged with the next cell below
            continue
        if out and out[-1] in ("$", "($") and cs:
            out[-1] = ("(" if out[-1] == "($" else "") + cs
            continue
        out.append(cs)
    return [c for c in out if c not in ("$", "($")]


def _rows_to_table(raw_rows: list[list[str]], kind: str) -> Table:
    rows: list[Row] = []
    for cells in raw_rows:
        cells = _merge_currency_cells(cells)
        non_empty = [c for c in cells if c.strip()]
        if not non_empty:
            continue
        # label = leading non-numeric cells joined; tokens = numeric-looking cells after it
        label_parts: list[str] = []
        tokens: list[str] = []
        for c in non_empty:
            if not tokens and not is_numeric_token(c) and not YEAR_ONLY(c):
                label_parts.append(c)
            else:
                tokens.append(c)
        rows.append(Row(label=clean_label(" ".join(label_parts)), tokens=tokens, raw=" | ".join(non_empty)))
    return Table(rows=rows, kind=kind)


def YEAR_ONLY(c: str) -> bool:
    return bool(re.fullmatch(r"(19[89]\d|20[0-2]\d)", c.strip()))


def parse_html(doc: str) -> Document:
    p = _GridParser()
    try:
        p.feed(doc)
        p.close()
    except Exception:  # noqa: BLE001 - be lenient with 1990s markup
        pass
    text = html.unescape("".join(p.out))
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    tables = [t for t in p.tables if t.rows]
    for t in tables:
        finalize(t)
    return Document(text=text, tables=tables, kind="html")


# --------------------------------------------------------------------------------------------
# fixed-width text (1990s .txt submissions)
# --------------------------------------------------------------------------------------------

VALUE_SPLIT_RE = re.compile(r"\s{2,}|\t")


def _text_row(line: str) -> Row | None:
    s = line.rstrip()
    if not s.strip():
        return None
    parts = [p for p in VALUE_SPLIT_RE.split(s.strip()) if p != ""]
    parts = _merge_currency_cells(parts)
    label_parts: list[str] = []
    tokens: list[str] = []
    for p in parts:
        # a cell like "$ 1,234" or "(1,234)" or "2004"
        if not tokens and not is_numeric_token(p) and not YEAR_ONLY(p) and not _all_years(p):
            label_parts.append(p)
        else:
            # tokens separated by single spaces inside one chunk: "1,234  5,678" handled by split; "$1,234 $5,678" here
            for sub in re.split(r"\s+(?=[\$\(\-\d])", p):
                tokens.append(sub)
    if not label_parts and not tokens:
        return None
    return Row(label=clean_label(" ".join(label_parts)), tokens=tokens, raw=s.strip())


def _all_years(chunk: str) -> bool:
    toks = chunk.split()
    return bool(toks) and all(YEAR_ONLY(t) for t in toks)


def parse_text(doc: str) -> Document:
    text = doc.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"<PAGE>\s*\d*", "\n", text, flags=re.I)
    lines = text.split("\n")
    tables: list[Table] = []
    i, n = 0, len(lines)
    offsets = []
    pos = 0
    for ln in lines:
        offsets.append(pos)
        pos += len(ln) + 1
    while i < n:
        line = lines[i]
        if len(YEAR_RE.findall(line)) >= 2 and len(line) < 200:
            # candidate header; collect a block of rows below it
            start = i
            j = i + 1
            blank = 0
            rows: list[Row] = []
            header_rows = [r for r in (_text_row(lines[k]) for k in range(max(0, i - 3), i + 1)) if r]
            while j < n and j - start < 120:
                s = lines[j]
                if not s.strip():
                    blank += 1
                    if blank >= 3:
                        break
                    j += 1
                    continue
                blank = 0
                if len(YEAR_RE.findall(s)) >= 2 and len(rows) > 3:
                    break  # next table's header
                r = _text_row(s)
                if r:
                    rows.append(r)
                j += 1
            if any(r.tokens for r in rows):
                t = Table(rows=header_rows + rows, kind="text", offset=offsets[start])
                t.preface = "\n".join(lines[max(0, start - 12):start])[-800:]
                finalize(t)
                tables.append(t)
            i = j
            continue
        i += 1
    return Document(text=text, tables=tables, kind="text")


def parse_document(body: str) -> Document:
    if re.search(r"<\s*(table|html|body|div|p)\b", body[:200000], re.I):
        return parse_html(body)
    return parse_text(body)


# --------------------------------------------------------------------------------------------
# header analysis
# --------------------------------------------------------------------------------------------


def detect_years(table: Table, max_header_rows: int = 8) -> list[int]:
    """Ordered list of fiscal-year labels for the value columns, from the first header rows."""
    best: list[int] = []
    for row in table.rows[:max_header_rows]:
        text = " ".join([row.label, *row.tokens]) if row.label else " ".join(row.tokens)
        # full dates (Jan. 31, 2005) or "fiscal 2004" are preferred when they cover the row; otherwise bare years
        by_date = [int(m.group(2)) for m in DATE_RE.finditer(text)]
        by_fiscal = [int(m.group(1)) for m in FISCAL_RE.finditer(text)]
        plain = [int(y) for y in YEAR_RE.findall(text)]
        years = max((by_date, by_fiscal, plain), key=len)
        # ignore "fiscal years 2004 through 2008" style prose: require the row to be mostly years
        if len(years) >= 2 and len(set(years)) >= 2 and _mostly_years(row):
            if len(years) > len(best):
                best = years
            if len(best) >= 3:
                break
    if len(best) >= 2:
        asc = all(a < b for a, b in zip(best, best[1:], strict=False))
        desc = all(a > b for a, b in zip(best, best[1:], strict=False))
        if not (asc or desc):
            # duplicated years (e.g. "2004 2004 2003") — de-duplicate preserving order
            seen: list[int] = []
            for y in best:
                if y not in seen:
                    seen.append(y)
            best = seen
    return best


def header_month(table: Table, max_header_rows: int = 8) -> int | None:
    """Month of the period-end dates in the header if they are spelled out (Jan. 31, 2005 -> 1)."""
    for row in table.rows[:max_header_rows]:
        text = " ".join([row.label, *row.tokens])
        m = DATE_RE.search(text)
        if m:
            return MONTHS[m.group(1).lower()[:3]]
    return None


def _mostly_years(row: Row) -> bool:
    txt = " ".join([row.label, *row.tokens])
    words = re.findall(r"[A-Za-z]{3,}", txt)
    non_year_words = [w for w in words if w.lower() not in (
        "fiscal", "year", "years", "ended", "ending", "december", "january", "february", "march", "april", "may",
        "june", "july", "august", "september", "october", "november", "as", "of", "at", "weeks", "months", "period",
        "restated", "unaudited", "dec", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov",
    )]
    return len(non_year_words) <= 3


def detect_scale(table: Table, fallback: float | None = None) -> tuple[float, str]:
    """Multiplier for money/share values ('in millions' -> 1e6). Per-share rows are exempt (caller)."""
    candidates = table.preface[-600:] + "\n" + "\n".join(r.raw for r in table.rows[:6])
    m = SCALE_RE.search(candidates)
    if m:
        word = (m.group(1) or "thousands").lower()
        return {"millions": 1e6, "thousands": 1e3, "billions": 1e9}.get(word, 1e3), m.group(0)
    if fallback:
        return fallback, "document default"
    return 1.0, ""


def document_scale(doc_text: str) -> float | None:
    """Dominant scale phrase in the whole document, used when a table has no scale note of its own."""
    counts = {"millions": 0, "thousands": 0, "billions": 0}
    for m in SCALE_RE.finditer(doc_text):
        w = (m.group(1) or "thousands").lower()
        counts[w] = counts.get(w, 0) + 1
    if not any(counts.values()):
        return None
    word = max(counts, key=lambda k: counts[k])
    return {"millions": 1e6, "thousands": 1e3, "billions": 1e9}[word]


def finalize(table: Table) -> None:
    table.years = detect_years(table)
    table.scale, table.scale_source = detect_scale(table)
