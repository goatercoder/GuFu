"""Shared dependencies, lookups and row->schema converters for the routers."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from sqlmodel import Session, select

from .. import catalog
from ..auth import require_admin
from ..db import get_session
from ..models import (
    Asset,
    CheckResult,
    Evidence,
    EvidenceLink,
    Organization,
    PoamItem,
    PoamMilestone,
    Provider,
    System,
    utcnow,
)
from ..schemas import (
    AgentReportRead,
    CheckResultRead,
    EvidenceLinkRead,
    EvidenceRead,
    PoamItemRead,
    PoamMilestoneRead,
)

SessionDep = Annotated[Session, Depends(get_session)]
ActorDep = Annotated[str, Depends(require_admin)]


def not_found(what: str, ident: Any) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{what} {ident} not found")


def bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


# --------------------------------------------------------------------------------------------
# Lookups
# --------------------------------------------------------------------------------------------
def get_organization(session: Session) -> Organization | None:
    return session.exec(select(Organization).order_by(Organization.id)).first()


def require_organization(session: Session) -> Organization:
    org = get_organization(session)
    if org is None:
        raise bad_request("Create the organization first (PUT /api/organization)")
    return org


def get_system_or_404(session: Session, system_id: int) -> System:
    system = session.get(System, system_id)
    if system is None:
        raise not_found("System", system_id)
    return system


def get_asset_or_404(session: Session, asset_id: int) -> Asset:
    asset = session.get(Asset, asset_id)
    if asset is None:
        raise not_found("Asset", asset_id)
    return asset


def get_provider_or_404(session: Session, provider_id: int) -> Provider:
    provider = session.get(Provider, provider_id)
    if provider is None:
        raise not_found("Provider", provider_id)
    return provider


def require_catalog_control(control_id: str) -> dict[str, Any]:
    ctrl = catalog.control(control_id)
    if ctrl is None:
        raise not_found("Control", control_id)
    return ctrl


# --------------------------------------------------------------------------------------------
# Converters (rows -> read schemas), reused by later stages
# --------------------------------------------------------------------------------------------
def _loads(text: str | None, default: Any) -> Any:
    if not text:
        return default
    try:
        return json.loads(text)
    except ValueError:
        return default


def to_check_result_read(row: CheckResult) -> CheckResultRead:
    return CheckResultRead(
        id=row.id,
        report_id=row.report_id,
        asset_id=row.asset_id,
        system_id=row.system_id,
        check_id=row.check_id,
        title=row.title,
        status=row.status,
        observed=row.observed,
        expected=row.expected,
        details=_loads(row.details_json, None),
        error=row.error,
        collected_at=row.collected_at,
        control_ids=_loads(row.control_ids_json, []),
        objective_ids=_loads(row.objective_ids_json, []),
        is_latest=row.is_latest,
        created_at=row.created_at,
    )


def to_agent_report_read(row) -> AgentReportRead:  # noqa: ANN001
    return AgentReportRead.model_validate(row)


def is_expired(expires_at: datetime | None, now: datetime | None = None) -> bool:
    if expires_at is None:
        return False
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at < (now or utcnow())


def to_evidence_read(row: Evidence, links: list[EvidenceLink] | None = None) -> EvidenceRead:
    data = EvidenceRead.model_validate(row)
    data.expired = is_expired(row.expires_at)
    data.links = [EvidenceLinkRead.model_validate(link) for link in (links or [])]
    return data


def to_poam_read(row: PoamItem, milestones: list[PoamMilestone] | None = None) -> PoamItemRead:
    data = PoamItemRead.model_validate(row)
    data.milestones = [
        PoamMilestoneRead.model_validate(m)
        for m in sorted(milestones or [], key=lambda m: (m.position, m.id or 0))
    ]
    return data


def links_by_evidence(session: Session, evidence_ids: list[int]) -> dict[int, list[EvidenceLink]]:
    out: dict[int, list[EvidenceLink]] = {eid: [] for eid in evidence_ids}
    if not evidence_ids:
        return out
    for link in session.exec(select(EvidenceLink).where(EvidenceLink.evidence_id.in_(evidence_ids))).all():
        out.setdefault(link.evidence_id, []).append(link)
    return out


def milestones_by_item(session: Session, item_ids: list[int]) -> dict[int, list[PoamMilestone]]:
    out: dict[int, list[PoamMilestone]] = {iid: [] for iid in item_ids}
    if not item_ids:
        return out
    for m in session.exec(select(PoamMilestone).where(PoamMilestone.poam_item_id.in_(item_ids))).all():
        out.setdefault(m.poam_item_id, []).append(m)
    return out
