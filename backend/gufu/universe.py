"""S&P 500 universe + ticker symbol conventions across data providers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class CompanyProfile:
    ticker: str  # canonical, e.g. BRK.B
    name: str
    sector: str
    sub_industry: str
    cik: int | None = None

    @property
    def yahoo_symbol(self) -> str:
        return yahoo_symbol(self.ticker)


def canonical_ticker(raw: str) -> str:
    return raw.strip().upper().replace("-", ".")


def yahoo_symbol(ticker: str) -> str:
    """Yahoo uses '-' for share classes: BRK.B -> BRK-B."""
    return ticker.upper().replace(".", "-")


def stooq_symbol(ticker: str) -> str:
    return f"{ticker.lower().replace('.', '-')}.us"


def sec_lookup_candidates(ticker: str) -> list[str]:
    """SEC's company_tickers.json usually uses '-' (BRK-B); try a few spellings."""
    t = ticker.upper()
    return list(dict.fromkeys([t, t.replace(".", "-"), t.replace(".", ""), t.replace(".", "/")]))


def load_sp500(path: Path) -> list[CompanyProfile]:
    with open(path, encoding="utf-8") as fh:
        rows = json.load(fh)
    out: list[CompanyProfile] = []
    for r in rows:
        out.append(
            CompanyProfile(
                ticker=canonical_ticker(r["ticker"]),
                name=r["name"],
                sector=r.get("sector", ""),
                sub_industry=r.get("sub_industry", ""),
                cik=int(r["cik"]) if r.get("cik") else None,
            )
        )
    return out


@lru_cache(maxsize=4)
def load_sp500_cached(path: str) -> tuple[CompanyProfile, ...]:
    return tuple(load_sp500(Path(path)))


def resolve_ciks(profiles: list[CompanyProfile], ticker_map: dict[str, int]) -> list[CompanyProfile]:
    """Attach CIKs from SEC's ticker map. Profiles already carrying a CIK keep it."""
    upper = {k.upper(): v for k, v in ticker_map.items()}
    resolved: list[CompanyProfile] = []
    for p in profiles:
        cik = p.cik
        if cik is None:
            for cand in sec_lookup_candidates(p.ticker):
                if cand in upper:
                    cik = upper[cand]
                    break
        resolved.append(CompanyProfile(p.ticker, p.name, p.sector, p.sub_industry, cik))
    return resolved


def search_companies(profiles: list[CompanyProfile], q: str, limit: int = 20) -> list[CompanyProfile]:
    q = q.strip().lower()
    if not q:
        return list(profiles[:limit])
    scored: list[tuple[int, CompanyProfile]] = []
    for p in profiles:
        t = p.ticker.lower()
        n = p.name.lower()
        if t == q:
            score = 0
        elif t.startswith(q):
            score = 1
        elif n.startswith(q):
            score = 2
        elif any(w.startswith(q) for w in n.replace("(", " ").split()):
            score = 3
        elif q in n or q in t:
            score = 4
        else:
            continue
        scored.append((score, p))
    scored.sort(key=lambda s: (s[0], s[1].ticker))
    return [p for _, p in scored[:limit]]
