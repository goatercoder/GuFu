"""Agent report ingestion: check results -> evidence, findings and POA&M items.

Implements ARCHITECTURE.md §6. The agents send only a check id and a status; every mapping to
security requirements and assessment objectives happens here, from ``catalog/checks.json``, so a
mapping change never requires redeploying endpoints.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta

from sqlmodel import Session, select

from . import catalog
from .activity import log_activity
from .config import Settings, get_settings
from .models import (
    AgentReport,
    Asset,
    AssetCategory,
    AssetType,
    CheckResult,
    CheckStatus,
    Evidence,
    EvidenceKind,
    EvidenceLink,
    EvidenceSource,
    PoamItem,
    PoamMilestone,
    PoamSource,
    PoamStatus,
    RiskLevel,
    System,
    utcnow,
)
from .schemas import AgentReportIn, IngestResponse

#: How long an asset may stay silent before its agent counts as stale.
STALE_AFTER = timedelta(hours=48)

#: Days given to remediate an automatically raised finding.
AUTO_POAM_DAYS = 30

OPEN_POAM_STATUSES = (PoamStatus.open, PoamStatus.in_progress)

_PLATFORM_ASSET_TYPE = {
    "windows": AssetType.workstation,
    "linux": AssetType.server,
    "macos": AssetType.workstation,
}

_RISK_BY_WEIGHT = {5: RiskLevel.high, 3: RiskLevel.moderate, 1: RiskLevel.low, 0: RiskLevel.low}


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def risk_for_weight(weight: int) -> RiskLevel:
    """Map a DoD Assessment Methodology point value onto a POA&M risk level."""
    return _RISK_BY_WEIGHT.get(weight, RiskLevel.moderate)


# --------------------------------------------------------------------------------------------
# Asset resolution
# --------------------------------------------------------------------------------------------
def resolve_asset(session: Session, system: System, payload: AgentReportIn) -> tuple[Asset, bool]:
    """Find the asset this report belongs to by hostname (case-insensitive), or create it.

    Auto-created assets are flagged ``needs_review`` so somebody confirms the CMMC asset
    category before the inventory is used in an assessment.
    """
    hostname = payload.asset.hostname.strip()
    assets = session.exec(select(Asset).where(Asset.system_id == system.id)).all()
    match = next((a for a in assets if (a.name or "").lower() == hostname.lower()), None)
    created = False
    if match is None:
        platform = (payload.asset.os_family or payload.agent.platform or "").lower()
        match = Asset(
            system_id=system.id,
            name=hostname,
            asset_type=_PLATFORM_ASSET_TYPE.get(platform, AssetType.workstation),
            category=AssetCategory.cui,
            category_rationale="Created automatically from an agent report; confirm the CMMC "
            "asset category and the rationale before relying on this inventory.",
            needs_review=True,
        )
        created = True
    match.os_family = payload.asset.os_family or match.os_family
    match.os_name = payload.asset.os_name or match.os_name
    match.os_version = payload.asset.os_version or match.os_version
    match.serial_number = payload.asset.serial_number or match.serial_number
    if payload.asset.ip_addresses:
        match.ip_address = payload.asset.ip_addresses[0]
    if payload.asset.mac_addresses:
        match.mac_address = payload.asset.mac_addresses[0]
    match.agent_platform = payload.agent.platform or payload.asset.os_family
    match.agent_version = payload.agent.version
    match.agent_last_seen = utcnow()
    match.updated_at = utcnow()
    session.add(match)
    session.flush()
    return match, created


# --------------------------------------------------------------------------------------------
# Ingestion
# --------------------------------------------------------------------------------------------
def ingest_report(
    session: Session,
    system: System,
    payload: AgentReportIn,
    settings: Settings | None = None,
    *,
    actor: str = "agent",
) -> IngestResponse:
    """Store a report, refresh evidence, and raise POA&M items for new failures.

    The caller commits. Returns the counts the agent prints back to the operator.
    """
    settings = settings or get_settings()
    asset, asset_created = resolve_asset(session, system, payload)
    collected_at = _as_utc(payload.collected_at) or utcnow()

    fail_count = sum(1 for c in payload.checks if str(c.status) == CheckStatus.fail.value)
    report = AgentReport(
        asset_id=asset.id,
        system_id=system.id,
        agent_version=payload.agent.version,
        platform=payload.agent.platform or payload.asset.os_family,
        hostname=payload.asset.hostname,
        collected_at=collected_at,
        received_at=utcnow(),
        raw_json=payload.model_dump_json(),
        check_count=len(payload.checks),
        fail_count=fail_count,
    )
    session.add(report)
    session.flush()
    asset.agent_last_report_id = report.id
    session.add(asset)

    unknown: list[str] = []
    for item in payload.checks:
        definition = catalog.check(item.check_id)
        if definition is None:
            unknown.append(item.check_id)
        _supersede(session, asset.id, item.check_id)
        result = CheckResult(
            report_id=report.id,
            asset_id=asset.id,
            system_id=system.id,
            check_id=item.check_id,
            title=(definition or {}).get("title"),
            status=str(item.status),
            observed=item.observed,
            expected=item.expected or (definition or {}).get("expected"),
            details_json=json.dumps(item.details) if item.details is not None else None,
            error=item.error,
            collected_at=collected_at,
            control_ids_json=json.dumps((definition or {}).get("control_ids", [])),
            objective_ids_json=json.dumps((definition or {}).get("objective_ids", [])),
            is_latest=True,
        )
        session.add(result)
        session.flush()
        if definition is not None:
            _upsert_check_evidence(session, system, asset, item, definition, collected_at, settings)

    session.flush()
    poam_created = 0
    if settings.auto_poam:
        poam_created = sync_poam_from_findings(session, system, actor=actor)

    log_activity(
        session,
        actor,
        "ingest",
        "agent_report",
        report.id,
        f"Agent report from {payload.asset.hostname}: {len(payload.checks)} checks, {fail_count} failing"
        + (" (new asset)" if asset_created else ""),
        system_id=system.id,
    )
    message = (
        f"Stored {len(payload.checks)} checks for {asset.name}: {fail_count} failing"
        + (f", {poam_created} POA&M item(s) opened" if poam_created else "")
        + (f", {len(unknown)} unknown check id(s)" if unknown else "")
    )
    return IngestResponse(
        asset_id=asset.id,
        system_id=system.id,
        checks_ingested=len(payload.checks),
        findings=fail_count,
        poam_created=poam_created,
        unknown_checks=unknown,
        message=message,
    )


def _supersede(session: Session, asset_id: int, check_id: str) -> None:
    """Clear ``is_latest`` on the previous result for this (asset, check)."""
    previous = session.exec(
        select(CheckResult).where(
            CheckResult.asset_id == asset_id,
            CheckResult.check_id == check_id,
            CheckResult.is_latest == True,  # noqa: E712 - SQL boolean column comparison
        )
    ).all()
    for row in previous:
        row.is_latest = False
        session.add(row)


def _upsert_check_evidence(
    session: Session,
    system: System,
    asset: Asset,
    item,  # schemas.CheckIn
    definition: dict,
    collected_at: datetime,
    settings: Settings,
) -> Evidence:
    """One evidence record per (asset, check), refreshed on every report.

    Agent evidence expires after ``BULWARK_EVIDENCE_TTL_DAYS`` so a device that stops reporting
    stops counting towards evidence coverage.
    """
    existing = session.exec(
        select(Evidence).where(
            Evidence.system_id == system.id,
            Evidence.asset_id == asset.id,
            Evidence.check_id == item.check_id,
            Evidence.source == EvidenceSource.agent,
        )
    ).first()
    title = f"{definition.get('title', item.check_id)} - {asset.name}"
    description = (item.observed or "")[:2000]
    expires_at = collected_at + timedelta(days=settings.evidence_ttl_days)
    if existing is None:
        existing = Evidence(
            system_id=system.id,
            title=title,
            kind=EvidenceKind.agent_check,
            description=description,
            source=EvidenceSource.agent,
            asset_id=asset.id,
            check_id=item.check_id,
        )
    existing.title = title
    existing.description = description
    existing.collected_at = collected_at
    existing.expires_at = expires_at
    existing.check_status = str(item.status)
    existing.updated_at = utcnow()
    session.add(existing)
    session.flush()

    wanted: set[tuple[str, str | None]] = set()
    for control_id in definition.get("control_ids", []):
        wanted.add((control_id, None))
    for objective_id in definition.get("objective_ids", []):
        wanted.add((catalog.control_id_for_objective(objective_id), objective_id))
    have = session.exec(select(EvidenceLink).where(EvidenceLink.evidence_id == existing.id)).all()
    present = {(row.control_id, row.objective_id) for row in have}
    for control_id, objective_id in sorted(wanted, key=lambda pair: (pair[0], pair[1] or "")):
        if (control_id, objective_id) not in present:
            session.add(
                EvidenceLink(evidence_id=existing.id, control_id=control_id, objective_id=objective_id)
            )
    return existing


# --------------------------------------------------------------------------------------------
# Findings
# --------------------------------------------------------------------------------------------
def latest_results(
    session: Session, system_id: int, *, statuses: Iterable[str] | None = None
) -> list[CheckResult]:
    """Current results for every (asset, check) pair in a system, newest report only."""
    query = select(CheckResult).where(
        CheckResult.system_id == system_id,
        CheckResult.is_latest == True,  # noqa: E712 - SQL boolean column comparison
    )
    rows = list(session.exec(query).all())
    if statuses is not None:
        wanted = set(statuses)
        rows = [row for row in rows if row.status in wanted]
    return rows


def findings_for_system(session: Session, system_id: int) -> list[dict]:
    """Failing checks grouped by (control, check) with the affected assets.

    Only assets that are in scope (category other than ``out_of_scope``) produce findings.
    """
    failing = latest_results(session, system_id, statuses={CheckStatus.fail.value})
    if not failing:
        return []
    asset_ids = {row.asset_id for row in failing}
    assets = {
        a.id: a
        for a in session.exec(select(Asset).where(Asset.id.in_(asset_ids))).all()  # type: ignore[union-attr]
    }
    open_items = session.exec(
        select(PoamItem).where(
            PoamItem.system_id == system_id,
            PoamItem.status.in_(OPEN_POAM_STATUSES),  # type: ignore[union-attr]
        )
    ).all()
    poam_by_key = {(item.control_id, item.check_id): item for item in open_items}
    poam_by_control: dict[str, PoamItem] = {}
    for item in open_items:
        poam_by_control.setdefault(item.control_id, item)

    grouped: dict[tuple[str, str], dict] = {}
    for row in failing:
        asset = assets.get(row.asset_id)
        if asset is None or asset.category == AssetCategory.out_of_scope:
            continue
        definition = catalog.check(row.check_id) or {}
        control_ids = json.loads(row.control_ids_json or "[]")
        for control_id in control_ids:
            control = catalog.control(control_id)
            if control is None:
                continue
            key = (control_id, row.check_id)
            entry = grouped.setdefault(
                key,
                {
                    "control_id": control_id,
                    "cmmc_id": control.get("cmmc_id"),
                    "control_name": control.get("name", ""),
                    "weight": control.get("weight", 0),
                    "check_id": row.check_id,
                    "check_title": definition.get("title", row.check_id),
                    "expected": row.expected or definition.get("expected"),
                    "remediation": definition.get("remediation"),
                    "objective_ids": json.loads(row.objective_ids_json or "[]"),
                    "assets": [],
                    "poam_item_id": None,
                },
            )
            entry["assets"].append(
                {
                    "asset_id": asset.id,
                    "asset_name": asset.name,
                    "status": row.status,
                    "observed": row.observed,
                    "collected_at": row.collected_at,
                }
            )
            item = poam_by_key.get(key) or poam_by_control.get(control_id)
            if item is not None:
                entry["poam_item_id"] = item.id

    out = []
    for entry in grouped.values():
        entry["assets"].sort(key=lambda a: a["asset_name"].lower())
        entry["asset_count"] = len(entry["assets"])
        out.append(entry)
    out.sort(key=lambda e: (-e["weight"], e["control_id"], e["check_id"]))
    return out


def sync_poam_from_findings(session: Session, system: System, *, actor: str = "agent") -> int:
    """Open a POA&M item for each new finding; note recovery on items that now pass.

    Never closes an item automatically: an assessor decides when a weakness is remediated.
    """
    findings = findings_for_system(session, system.id)
    open_items = session.exec(
        select(PoamItem).where(
            PoamItem.system_id == system.id,
            PoamItem.source == PoamSource.agent,
            PoamItem.status.in_(OPEN_POAM_STATUSES),  # type: ignore[union-attr]
        )
    ).all()
    by_key = {(item.control_id, item.check_id): item for item in open_items}
    failing_keys = {(f["control_id"], f["check_id"]) for f in findings}
    today = date.today()
    created = 0

    for finding in findings:
        key = (finding["control_id"], finding["check_id"])
        if key in by_key:
            continue
        # An item for the same control raised by a human keeps ownership of the weakness.
        duplicate = session.exec(
            select(PoamItem).where(
                PoamItem.system_id == system.id,
                PoamItem.control_id == finding["control_id"],
                PoamItem.status.in_(OPEN_POAM_STATUSES),  # type: ignore[union-attr]
            )
        ).first()
        if duplicate is not None:
            continue
        names = ", ".join(a["asset_name"] for a in finding["assets"][:5])
        more = "" if len(finding["assets"]) <= 5 else f" and {len(finding['assets']) - 5} more"
        item = PoamItem(
            system_id=system.id,
            control_id=finding["control_id"],
            title=f"{finding['check_title']} failing on {finding['asset_count']} asset(s)",
            weakness_description=(
                f"Automated check {finding['check_id']} is failing on: {names}{more}. "
                f"Expected: {finding['expected'] or 'see check definition'}. "
                f"Latest observation: {finding['assets'][0]['observed'] or 'n/a'}."
            ),
            source=PoamSource.agent,
            risk_level=risk_for_weight(finding["weight"]),
            status=PoamStatus.open,
            identified_at=today,
            scheduled_completion=today + timedelta(days=AUTO_POAM_DAYS),
            remediation_plan=finding["remediation"],
            check_id=finding["check_id"],
            asset_id=finding["assets"][0]["asset_id"],
        )
        session.add(item)
        session.flush()
        session.add(
            PoamMilestone(
                poam_item_id=item.id,
                description=f"Remediate {finding['check_title']} on all affected assets and confirm "
                "the automated check passes",
                due_date=today + timedelta(days=AUTO_POAM_DAYS),
                position=0,
            )
        )
        log_activity(
            session,
            actor,
            "create",
            "poam_item",
            item.id,
            f"Opened automatically from failing check {finding['check_id']} ({finding['control_id']})",
            system_id=system.id,
        )
        created += 1

    stamp = utcnow().strftime("%Y-%m-%d %H:%M UTC")
    for key, item in by_key.items():
        if key in failing_keys:
            continue
        marker = f"[{stamp}] Automated check {item.check_id} is now passing on all in-scope assets."
        if item.notes and marker.split("]")[-1] in item.notes:
            continue
        item.notes = f"{item.notes}\n{marker}" if item.notes else marker
        item.updated_at = utcnow()
        session.add(item)
        log_activity(
            session,
            actor,
            "update",
            "poam_item",
            item.id,
            f"Check {item.check_id} passing again; item left open for assessor review",
            system_id=system.id,
        )
    return created


# --------------------------------------------------------------------------------------------
# Agent status
# --------------------------------------------------------------------------------------------
def agent_status(session: Session, system_id: int) -> list[dict]:
    """Per-asset agent health: last seen, version and the latest pass/fail/error counts."""
    assets = session.exec(
        select(Asset).where(Asset.system_id == system_id, Asset.agent_last_seen.is_not(None))  # type: ignore[union-attr]
    ).all()
    rows = latest_results(session, system_id)
    counts: dict[int, dict[str, int]] = {}
    for row in rows:
        bucket = counts.setdefault(row.asset_id, {})
        bucket[row.status] = bucket.get(row.status, 0) + 1
    now = utcnow()
    out = []
    for asset in sorted(assets, key=lambda a: a.name.lower()):
        bucket = counts.get(asset.id, {})
        last_seen = _as_utc(asset.agent_last_seen)
        out.append(
            {
                "asset_id": asset.id,
                "asset_name": asset.name,
                "hostname": asset.name,
                "category": asset.category,
                "platform": asset.agent_platform,
                "agent_version": asset.agent_version,
                "last_seen": last_seen,
                "stale": last_seen is None or (now - last_seen) > STALE_AFTER,
                "pass_count": bucket.get(CheckStatus.passed.value, 0),
                "fail_count": bucket.get(CheckStatus.fail.value, 0),
                "error_count": bucket.get(CheckStatus.error.value, 0),
                "info_count": bucket.get(CheckStatus.info.value, 0),
                "not_applicable_count": bucket.get(CheckStatus.not_applicable.value, 0),
            }
        )
    return out
