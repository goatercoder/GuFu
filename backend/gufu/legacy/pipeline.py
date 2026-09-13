"""Fetch, extract and store pre-XBRL financial history for one company."""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from gufu.legacy.extract import Extraction, extract_filing
from gufu.legacy.merge import FilingResult, LegacyData, merge_filings
from gufu.legacy.submissions import (
    FilingRef,
    ex13_links,
    page_names,
    parse_submissions,
    select_filings,
    split_sgml,
    tenk_filings,
    wanted_sgml_documents,
)

log = logging.getLogger("gufu.legacy")
MAX_DOC_BYTES = 20 * 1024 * 1024


class LegacyUnavailable(RuntimeError):
    pass


async def _cached_document(fetchers, repo, cik: int, accn: str, name: str, url: str) -> str:
    hit = repo.get_legacy_doc(cik, accn, name)
    if hit is not None:
        return hit
    body = await fetchers.document(url)
    if len(body) > MAX_DOC_BYTES:
        body = body[:MAX_DOC_BYTES]
    repo.put_legacy_doc(cik, accn, name, body)
    return body


async def _filing_documents(fetchers, repo, cik: int, f: FilingRef) -> tuple[list[str], list[str]]:
    """Return (document bodies, document names) for one filing: primary 10-K text (+ EX-13 when needed)."""
    names: list[str] = []
    bodies: list[str] = []
    if f.primary_doc and not f.primary_doc.lower().endswith(".txt"):
        primary = await _cached_document(fetchers, repo, cik, f.accn, f.primary_doc, f.primary_url(cik))
        bodies.append(primary)
        names.append(f.primary_doc)
        first = await asyncio.to_thread(extract_filing, [primary])
        if not (first.sections.get("summary") and first.sections.get("income")):
            # Item 6 / statements incorporated by reference -> look for the annual-report exhibit
            try:
                index_html = await _cached_document(fetchers, repo, cik, f.accn, "index.htm", f.index_url(cik))
                links = ex13_links(index_html, f.base_url(cik))
            except Exception as exc:  # noqa: BLE001
                log.debug("index page failed for %s: %s", f.accn, exc)
                links = []
            for url in links:
                name = url.rsplit("/", 1)[-1]
                try:
                    bodies.append(await _cached_document(fetchers, repo, cik, f.accn, name, url))
                    names.append(name)
                except Exception as exc:  # noqa: BLE001
                    log.debug("EX-13 fetch failed %s: %s", url, exc)
            if len(bodies) == 1:
                # last resort: the full submission text has every document
                try:
                    full = await _cached_document(fetchers, repo, cik, f.accn, "full.txt", f.full_txt_url(cik))
                    for t in wanted_sgml_documents(split_sgml(full))[1:]:
                        bodies.append(t)
                        names.append("EX-13 (from full submission)")
                except Exception as exc:  # noqa: BLE001
                    log.debug("full submission fetch failed for %s: %s", f.accn, exc)
    else:
        full = await _cached_document(fetchers, repo, cik, f.accn, "full.txt", f.full_txt_url(cik))
        for i, t in enumerate(wanted_sgml_documents(split_sgml(full))):
            bodies.append(t)
            names.append("10-K text" if i == 0 else f"EX-13 #{i}")
    return bodies, names


async def build_legacy(fetchers, repo, cik: int, fye_month: int, first_xbrl_fy: int, *, max_filings: int = 6,
                       force: bool = False) -> LegacyData:
    if not force:
        cached = repo.get_legacy(cik)
        if cached is not None:
            return LegacyData.from_dict(cached)
    main = await fetchers.submissions(cik)
    pages = []
    for name in page_names(main):
        try:
            pages.append(await fetchers.submissions_page(name))
        except Exception as exc:  # noqa: BLE001
            log.warning("submissions page %s failed: %s", name, exc)
    rows = parse_submissions(main, pages)
    filings = tenk_filings(rows, fye_month)
    chosen = select_filings(filings, first_xbrl_fy, max_filings=max_filings)
    results: list[FilingResult] = []
    warnings: list[str] = []
    for f in chosen:
        try:
            bodies, names = await _filing_documents(fetchers, repo, cik, f)
            ex: Extraction = await asyncio.to_thread(extract_filing, bodies)
            results.append(FilingResult(f.accn, f.form, f.filed, f.fiscal_year, f.human_url(cik), ex, names))
        except Exception as exc:  # noqa: BLE001
            log.warning("legacy filing %s (%s) failed for CIK %s: %s", f.accn, f.form, cik, exc)
            warnings.append(f"{f.form} filed {f.filed.isoformat()}: could not be fetched or parsed ({exc})")
    data = merge_filings(cik, results, first_xbrl_fy)
    data.warnings = warnings + data.warnings
    if not chosen:
        data.warnings.append(f"no 10-K filings before FY{first_xbrl_fy} found on EDGAR for this CIK")
    data.filings.sort(key=lambda d: d["filed"])
    repo.put_legacy(cik, data.to_dict())
    return data


def coverage(first_xbrl_fy: int | None, last_xbrl_fy: int | None, legacy_years: list[int], today: date | None = None) -> dict:
    today = today or date.today()
    window_from = (last_xbrl_fy or today.year) - 29
    have = set(legacy_years) | set(range(first_xbrl_fy, last_xbrl_fy + 1) if first_xbrl_fy and last_xbrl_fy else [])
    missing = [y for y in range(window_from, (last_xbrl_fy or today.year) + 1) if y not in have]
    return {
        "window_from": window_from, "window_to": last_xbrl_fy, "xbrl_from": first_xbrl_fy, "xbrl_to": last_xbrl_fy,
        "legacy_from": min(legacy_years) if legacy_years else None, "legacy_to": max(legacy_years) if legacy_years else None,
        "years_available": len(have & set(range(window_from, (last_xbrl_fy or today.year) + 1))), "missing_years": missing,
    }
