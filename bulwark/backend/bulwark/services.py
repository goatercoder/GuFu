"""Domain operations shared by several routers (and by later stages: ingestion, seeding, scoring).

* seeding the 110 control implementations (+320 objective assessments) for a new system,
* explicit cascade deletion of everything a system / provider / asset owns,
* lightweight per-system score summaries derived from implementation statuses.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from sqlalchemy import delete as sa_delete
from sqlalchemy import func
from sqlalchemy import update as sa_update
from sqlmodel import Session, select

from . import catalog
from .models import (
    MET_STATUSES,
    ActivityLog,
    AgentReport,
    Asset,
    CheckResult,
    ControlImplementation,
    Evidence,
    EvidenceLink,
    EvidenceSource,
    ObjectiveAssessment,
    PoamItem,
    PoamMilestone,
    Provider,
    ResponsibilityRow,
    ScoreSnapshot,
    System,
)


# --------------------------------------------------------------------------------------------
# Seeding
# --------------------------------------------------------------------------------------------
def seed_implementations(session: Session, system: System) -> int:
    """Create a ``control_implementation`` row per catalog control (``not_implemented``,
    ``customer``) plus one ``objective_assessment`` (``unknown``) per objective. Idempotent:
    existing rows are kept. Returns the number of implementations created."""
    assert system.id is not None
    existing = {
        impl.control_id: impl
        for impl in session.exec(
            select(ControlImplementation).where(ControlImplementation.system_id == system.id)
        ).all()
    }
    created: list[tuple[ControlImplementation, list[str]]] = []
    for ctrl in catalog.controls():
        if ctrl["id"] in existing:
            continue
        impl = ControlImplementation(system_id=system.id, control_id=ctrl["id"])
        session.add(impl)
        created.append((impl, [o["id"] for o in ctrl.get("objectives", [])]))
    if created:
        session.flush()
        for impl, objective_ids in created:
            for objective_id in objective_ids:
                session.add(ObjectiveAssessment(implementation_id=impl.id, objective_id=objective_id))
        session.flush()
    for impl in existing.values():
        ensure_objectives(session, impl)
    return len(created)


def ensure_objectives(session: Session, impl: ControlImplementation) -> int:
    """Create any objective_assessment rows missing for an implementation (self-healing)."""
    assert impl.id is not None
    present = set(
        session.exec(
            select(ObjectiveAssessment.objective_id).where(ObjectiveAssessment.implementation_id == impl.id)
        ).all()
    )
    added = 0
    for objective_id in catalog.objective_ids_for(impl.control_id):
        if objective_id not in present:
            session.add(ObjectiveAssessment(implementation_id=impl.id, objective_id=objective_id))
            added += 1
    if added:
        session.flush()
    return added


def get_implementation(session: Session, system_id: int, control_id: str) -> ControlImplementation | None:
    return session.exec(
        select(ControlImplementation).where(
            ControlImplementation.system_id == system_id,
            ControlImplementation.control_id == control_id,
        )
    ).first()


def ensure_implementation(session: Session, system_id: int, control_id: str) -> ControlImplementation:
    """Return the implementation row for (system, control), creating it if the catalog grew."""
    impl = get_implementation(session, system_id, control_id)
    if impl is None:
        impl = ControlImplementation(system_id=system_id, control_id=control_id)
        session.add(impl)
        session.flush()
    ensure_objectives(session, impl)
    return impl


# --------------------------------------------------------------------------------------------
# Cascades (explicit, so they work even if PRAGMA foreign_keys were off)
# --------------------------------------------------------------------------------------------
def delete_system_cascade(session: Session, system: System) -> None:
    """Delete a system and everything it owns; activity rows keep their history with
    ``system_id`` set to NULL."""
    sid = system.id
    assert sid is not None
    impl_ids = select(ControlImplementation.id).where(ControlImplementation.system_id == sid)
    evidence_ids = select(Evidence.id).where(Evidence.system_id == sid)
    poam_ids = select(PoamItem.id).where(PoamItem.system_id == sid)

    session.execute(sa_delete(CheckResult).where(CheckResult.system_id == sid))
    session.execute(sa_delete(AgentReport).where(AgentReport.system_id == sid))
    session.execute(sa_delete(EvidenceLink).where(EvidenceLink.evidence_id.in_(evidence_ids)))
    session.execute(sa_delete(Evidence).where(Evidence.system_id == sid))
    session.execute(sa_delete(PoamMilestone).where(PoamMilestone.poam_item_id.in_(poam_ids)))
    session.execute(sa_delete(PoamItem).where(PoamItem.system_id == sid))
    session.execute(sa_delete(ObjectiveAssessment).where(ObjectiveAssessment.implementation_id.in_(impl_ids)))
    session.execute(sa_delete(ControlImplementation).where(ControlImplementation.system_id == sid))
    session.execute(sa_delete(ScoreSnapshot).where(ScoreSnapshot.system_id == sid))
    session.execute(sa_delete(Asset).where(Asset.system_id == sid))
    session.execute(sa_update(ActivityLog).where(ActivityLog.system_id == sid).values(system_id=None))
    session.delete(system)
    session.flush()


def delete_provider_cascade(session: Session, provider: Provider) -> None:
    """Delete a provider, its responsibility matrix, and unlink implementations that used it."""
    pid = provider.id
    assert pid is not None
    session.execute(sa_delete(ResponsibilityRow).where(ResponsibilityRow.provider_id == pid))
    session.execute(
        sa_update(ControlImplementation)
        .where(ControlImplementation.provider_id == pid)
        .values(provider_id=None)
    )
    session.delete(provider)
    session.flush()


def delete_asset_cascade(session: Session, asset: Asset) -> None:
    """Delete an asset with its check results, reports and agent-generated evidence. Manually
    uploaded evidence and POA&M items that referenced the asset are kept with ``asset_id`` NULL."""
    aid = asset.id
    assert aid is not None
    agent_evidence_ids = select(Evidence.id).where(
        Evidence.asset_id == aid, Evidence.source == EvidenceSource.agent
    )
    session.execute(sa_delete(EvidenceLink).where(EvidenceLink.evidence_id.in_(agent_evidence_ids)))
    session.execute(
        sa_delete(Evidence).where(Evidence.asset_id == aid, Evidence.source == EvidenceSource.agent)
    )
    session.execute(sa_update(Evidence).where(Evidence.asset_id == aid).values(asset_id=None))
    session.execute(sa_update(PoamItem).where(PoamItem.asset_id == aid).values(asset_id=None))
    session.execute(sa_delete(CheckResult).where(CheckResult.asset_id == aid))
    session.execute(sa_delete(AgentReport).where(AgentReport.asset_id == aid))
    session.delete(asset)
    session.flush()


# --------------------------------------------------------------------------------------------
# Summaries
# --------------------------------------------------------------------------------------------
def score_summaries(session: Session, system_ids: Iterable[int]) -> dict[int, dict[str, int]]:
    """``{system_id: {"met_count": n, "total": m}}`` from implementation statuses.

    ``met`` follows ARCHITECTURE.md §5.1: ``implemented`` or ``not_applicable``. Stage 3's
    ``scoring.py`` provides the full SPRS computation; this is the lightweight list summary.
    """
    ids = list(system_ids)
    result: dict[int, dict[str, int]] = {sid: {"met_count": 0, "total": 0} for sid in ids}
    if not ids:
        return result
    rows = session.exec(
        select(ControlImplementation.system_id, ControlImplementation.status, func.count())
        .where(ControlImplementation.system_id.in_(ids))
        .group_by(ControlImplementation.system_id, ControlImplementation.status)
    ).all()
    for sid, status_value, count in rows:
        entry = result.setdefault(sid, {"met_count": 0, "total": 0})
        entry["total"] += count
        if status_value in MET_STATUSES:
            entry["met_count"] += count
    return result


def asset_counts(session: Session, system_ids: Iterable[int]) -> dict[int, int]:
    ids = list(system_ids)
    counts: dict[int, int] = defaultdict(int)
    if not ids:
        return counts
    rows = session.exec(
        select(Asset.system_id, func.count()).where(Asset.system_id.in_(ids)).group_by(Asset.system_id)
    ).all()
    for sid, count in rows:
        counts[sid] = count
    return counts
