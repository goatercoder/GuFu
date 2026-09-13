"""Combine legacy extractions across filings and turn them into PeriodRows next to the XBRL years."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from gufu.legacy.extract import Extraction
from gufu.xbrl import periods as P
from gufu.xbrl.models import PeriodRow
from gufu.xbrl.normalize import _add_derived

SEC_FILING_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accn_nodash}/"


@dataclass
class FilingResult:
    accn: str
    form: str
    filed: date
    fiscal_year: int | None
    url: str
    extraction: Extraction
    documents: list[str] = field(default_factory=list)  # document names fetched


@dataclass
class LegacyData:
    cik: int
    years: dict[int, dict[str, float]] = field(default_factory=dict)
    provenance: dict[int, dict[str, dict[str, Any]]] = field(default_factory=dict)
    filings: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    first_xbrl_fy: int | None = None

    def to_dict(self) -> dict:
        return {
            "cik": self.cik,
            "years": {str(k): v for k, v in sorted(self.years.items())},
            "provenance": {str(k): v for k, v in sorted(self.provenance.items())},
            "filings": self.filings,
            "warnings": self.warnings,
            "first_xbrl_fy": self.first_xbrl_fy,
        }

    @classmethod
    def from_dict(cls, d: dict) -> LegacyData:
        return cls(
            cik=d["cik"],
            years={int(k): v for k, v in d.get("years", {}).items()},
            provenance={int(k): v for k, v in d.get("provenance", {}).items()},
            filings=list(d.get("filings", [])),
            warnings=list(d.get("warnings", [])),
            first_xbrl_fy=d.get("first_xbrl_fy"),
        )


def merge_filings(cik: int, results: list[FilingResult], first_xbrl_fy: int | None) -> LegacyData:
    """Later filings win (restatements), statements beat the summary within one filing (already ordered)."""
    data = LegacyData(cik=cik, first_xbrl_fy=first_xbrl_fy)
    for r in sorted(results, key=lambda r: r.filed, reverse=True):
        data.filings.append({
            "accn": r.accn, "form": r.form, "filed": r.filed.isoformat(), "fiscal_year": r.fiscal_year, "url": r.url,
            "years": sorted(r.extraction.years.keys()), "documents": r.documents,
            "sections": r.extraction.sections,
        })
        for fy, vals in r.extraction.years.items():
            if first_xbrl_fy is not None and fy >= first_xbrl_fy:
                continue  # XBRL covers it
            for fld, v in vals.items():
                if fld in data.years.get(fy, {}):
                    continue
                data.years.setdefault(fy, {})[fld] = v
                data.provenance.setdefault(fy, {})[fld] = {
                    "accn": r.accn, "form": r.form, "filed": r.filed.isoformat(), "url": r.url,
                    "method": r.extraction.methods.get(fy, {}).get(fld, "summary"), "filing_fy": r.fiscal_year,
                }
        for w in r.extraction.warnings:
            tag = f"[{r.form} filed {r.filed.isoformat()}] {w}"
            if tag not in data.warnings:
                data.warnings.append(tag)
    return data


def legacy_rows(data: LegacyData, fye_month: int, exclude_fys: set[int]) -> list[PeriodRow]:
    rows: list[PeriodRow] = []
    for fy in sorted(data.years):
        if fy in exclude_fys:
            continue
        vals = data.years[fy]
        if not any(k in vals for k in ("revenue", "net_income", "total_assets", "eps_diluted")):
            continue
        end = P.month_end(fy, fye_month)
        start = P.shift_months(end, -12) + P.timedelta(days=1)
        prov = data.provenance.get(fy, {})
        filed = None
        for p in prov.values():
            try:
                d = date.fromisoformat(p["filed"])
            except (KeyError, ValueError):
                continue
            filed = d if filed is None or d > filed else filed
        row = PeriodRow(
            key=f"{fy:04d}-{fye_month:02d}", end=end, start=start, fiscal_year=fy, fiscal_quarter=None,
            form="10-K (legacy)", filed=filed, values=dict(vals),
            sources={k: f"legacy:{prov.get(k, {}).get('method', 'summary')}" for k in vals},
            derived={"legacy"},
        )
        _add_derived(row)
        rows.append(row)
    return rows


def period_source(data: LegacyData, fy: int) -> dict[str, Any] | None:
    prov = data.provenance.get(fy)
    if not prov:
        return None
    # the filing that supplied most fields for this year
    counts: dict[str, int] = {}
    meta: dict[str, dict] = {}
    for p in prov.values():
        counts[p["accn"]] = counts.get(p["accn"], 0) + 1
        meta[p["accn"]] = p
    accn = max(counts, key=lambda a: counts[a])
    m = meta[accn]
    methods = sorted({p["method"].split(" ")[0] for p in prov.values()})
    return {"accn": accn, "form": m["form"], "filed": m["filed"], "url": m["url"], "filing_fy": m.get("filing_fy"),
            "methods": methods, "fields": {k: p["method"] for k, p in prov.items()}}
