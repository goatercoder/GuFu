"""Data structures produced by the normalizer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass
class Fact:
    tag: str
    prio: int
    start: date | None
    end: date
    val: float
    accn: str
    form: str
    filed: date
    frame: str | None
    cls: str | None = None  # Q | H | 9M | FY for durations
    derived: bool = False


@dataclass
class PeriodRow:
    key: str  # 'YYYY-MM' fiscal month key
    end: date
    start: date | None
    fiscal_year: int
    fiscal_quarter: int | None  # None for annual rows
    form: str
    filed: date | None
    values: dict[str, float | None] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)
    derived: set[str] = field(default_factory=set)

    def label(self) -> str:
        if self.fiscal_quarter is None:
            return f"FY{self.fiscal_year}"
        return f"Q{self.fiscal_quarter} FY{self.fiscal_year}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "end": self.end.isoformat(),
            "start": self.start.isoformat() if self.start else None,
            "fy": self.fiscal_year,
            "fq": self.fiscal_quarter,
            "label": self.label(),
            "form": self.form,
            "filed": self.filed.isoformat() if self.filed else None,
            "v": {k: v for k, v in self.values.items() if v is not None},
            "src": self.sources,
            "derived": sorted(self.derived),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PeriodRow:
        return cls(
            key=d["key"],
            end=date.fromisoformat(d["end"]),
            start=date.fromisoformat(d["start"]) if d.get("start") else None,
            fiscal_year=d["fy"],
            fiscal_quarter=d.get("fq"),
            form=d.get("form", ""),
            filed=date.fromisoformat(d["filed"]) if d.get("filed") else None,
            values=dict(d.get("v", {})),
            sources=dict(d.get("src", {})),
            derived=set(d.get("derived", [])),
        )


@dataclass
class Financials:
    cik: int
    entity_name: str
    fye_month: int
    annual: list[PeriodRow]
    quarterly: list[PeriodRow]
    ttm: PeriodRow | None
    warnings: list[str] = field(default_factory=list)
    latest_10k_filed: date | None = None
    latest_10q_filed: date | None = None
    latest_filed: date | None = None
    legacy: Any = None  # LegacyData merged into `annual` at read time (never serialised here)

    @property
    def xbrl_annual(self) -> list[PeriodRow]:
        return [r for r in self.annual if "legacy" not in r.derived]

    def to_dict(self) -> dict[str, Any]:
        return {
            "cik": self.cik,
            "entity_name": self.entity_name,
            "fye_month": self.fye_month,
            "annual": [r.to_dict() for r in self.annual],
            "quarterly": [r.to_dict() for r in self.quarterly],
            "ttm": self.ttm.to_dict() if self.ttm else None,
            "warnings": self.warnings,
            "latest_10k_filed": self.latest_10k_filed.isoformat() if self.latest_10k_filed else None,
            "latest_10q_filed": self.latest_10q_filed.isoformat() if self.latest_10q_filed else None,
            "latest_filed": self.latest_filed.isoformat() if self.latest_filed else None,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Financials:
        def pd(s):
            return date.fromisoformat(s) if s else None

        return cls(
            cik=d["cik"],
            entity_name=d.get("entity_name", ""),
            fye_month=d.get("fye_month", 12),
            annual=[PeriodRow.from_dict(r) for r in d.get("annual", [])],
            quarterly=[PeriodRow.from_dict(r) for r in d.get("quarterly", [])],
            ttm=PeriodRow.from_dict(d["ttm"]) if d.get("ttm") else None,
            warnings=list(d.get("warnings", [])),
            latest_10k_filed=pd(d.get("latest_10k_filed")),
            latest_10q_filed=pd(d.get("latest_10q_filed")),
            latest_filed=pd(d.get("latest_filed")),
        )

    @property
    def latest_balance(self) -> PeriodRow | None:
        """Most recent row (quarterly or annual) carrying a balance sheet."""
        rows = [r for r in self.quarterly + self.annual if r.values.get("total_assets") is not None]
        if not rows:
            return None
        return max(rows, key=lambda r: (r.end, r.fiscal_quarter is not None))
