"""``/api/systems/{id}/controls``: per-system control implementation status and objectives."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlmodel import Session, select

from .. import catalog
from ..activity import log_activity
from ..auth import require_admin
from ..models import (
    OPEN_POAM_STATUSES,
    PARTIAL_CREDIT_CONTROLS,
    Asset,
    AssetCategory,
    CheckResult,
    CheckStatus,
    ControlImplementation,
    Evidence,
    EvidenceLink,
    ImplementationStatus,
    ObjectiveAssessment,
    ObjectiveStatus,
    PartialCredit,
    PoamItem,
    Provider,
    Responsibility,
    ResponsibilityRow,
    utcnow,
)
from ..schemas import (
    BulkControlItem,
    BulkControlResponse,
    CheckSummary,
    ControlDetail,
    ControlListItem,
    ImplementationRead,
    ImplementationUpdate,
    ObjectiveCounts,
    ObjectiveRead,
    ObjectiveUpdateItem,
)
from ..services import ensure_implementation, get_implementation, seed_implementations
from .deps import (
    ActorDep,
    SessionDep,
    bad_request,
    get_system_or_404,
    links_by_evidence,
    milestones_by_item,
    require_catalog_control,
    to_check_result_read,
    to_evidence_read,
    to_poam_read,
)
from .providers import matrix_row_read

router = APIRouter(
    prefix="/systems/{system_id}/controls", tags=["controls"], dependencies=[Depends(require_admin)]
)

PROVIDER_RESPONSIBILITIES = frozenset(
    {Responsibility.provider, Responsibility.shared, Responsibility.inherited}
)


# --------------------------------------------------------------------------------------------
# Aggregations
# --------------------------------------------------------------------------------------------
def _objective_counts(session: Session, system_id: int) -> dict[int, ObjectiveCounts]:
    rows = session.exec(
        select(ObjectiveAssessment.implementation_id, ObjectiveAssessment.status, func.count())
        .join(ControlImplementation, ControlImplementation.id == ObjectiveAssessment.implementation_id)
        .where(ControlImplementation.system_id == system_id)
        .group_by(ObjectiveAssessment.implementation_id, ObjectiveAssessment.status)
    ).all()
    counts: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for impl_id, status_value, count in rows:
        key = status_value.value if isinstance(status_value, ObjectiveStatus) else str(status_value)
        counts[impl_id][key] += count
        counts[impl_id]["total"] += count
    return {impl_id: ObjectiveCounts(**values) for impl_id, values in counts.items()}


def _evidence_counts(session: Session, system_id: int) -> dict[str, int]:
    rows = session.exec(
        select(EvidenceLink.control_id, func.count(func.distinct(EvidenceLink.evidence_id)))
        .join(Evidence, Evidence.id == EvidenceLink.evidence_id)
        .where(Evidence.system_id == system_id)
        .group_by(EvidenceLink.control_id)
    ).all()
    return {control_id: count for control_id, count in rows}


def _open_poam_counts(session: Session, system_id: int) -> dict[str, int]:
    rows = session.exec(
        select(PoamItem.control_id, func.count())
        .where(PoamItem.system_id == system_id, PoamItem.status.in_(list(OPEN_POAM_STATUSES)))
        .group_by(PoamItem.control_id)
    ).all()
    return {control_id: count for control_id, count in rows}


def _latest_results(session: Session, system_id: int) -> list[CheckResult]:
    """Latest check results for the system, excluding assets categorised out of scope."""
    return list(
        session.exec(
            select(CheckResult)
            .join(Asset, Asset.id == CheckResult.asset_id)
            .where(
                CheckResult.system_id == system_id,
                CheckResult.is_latest == True,  # noqa: E712
                Asset.category != AssetCategory.out_of_scope,
            )
            .order_by(CheckResult.check_id, CheckResult.asset_id)
        ).all()
    )


def _summarise(results: list[CheckResult]) -> CheckSummary | None:
    if not results:
        return None
    summary = CheckSummary(total=len(results))
    assets: set[int] = set()
    last: datetime | None = None
    for row in results:
        assets.add(row.asset_id)
        if row.status == CheckStatus.passed.value:
            summary.passing += 1
        elif row.status == CheckStatus.fail.value:
            summary.failing += 1
        elif row.status == CheckStatus.error.value:
            summary.errors += 1
        elif row.status == CheckStatus.not_applicable.value:
            summary.not_applicable += 1
        else:
            summary.info += 1
        if row.collected_at and (last is None or row.collected_at > last):
            last = row.collected_at
    summary.assets = len(assets)
    summary.last_collected_at = last
    return summary


def _results_by_control(results: list[CheckResult]) -> dict[str, list[CheckResult]]:
    grouped: dict[str, list[CheckResult]] = defaultdict(list)
    for row in results:
        try:
            control_ids = json.loads(row.control_ids_json or "[]")
        except ValueError:
            control_ids = []
        for control_id in control_ids:
            grouped[control_id].append(row)
    return grouped


def implementation_warnings(impl: ControlImplementation, counts: ObjectiveCounts | None) -> list[str]:
    """Assessor-facing consistency warnings (ARCHITECTURE.md §5.1-5.2 and readiness signals)."""
    warnings: list[str] = []
    status_value = ImplementationStatus(impl.status)
    if status_value == ImplementationStatus.not_applicable and not (impl.na_justification or "").strip():
        warnings.append("Marked not applicable without a justification")
    if status_value == ImplementationStatus.implemented and counts and counts.not_met:
        warnings.append(
            f"Marked implemented but {counts.not_met} objective(s) are not met; "
            "scored as partially implemented"
        )
    if Responsibility(impl.responsibility) in PROVIDER_RESPONSIBILITIES and impl.provider_id is None:
        warnings.append(f"Responsibility is '{impl.responsibility}' but no provider is linked")
    if (
        PartialCredit(impl.partial_credit) != PartialCredit.none
        and status_value != ImplementationStatus.partially_implemented
    ):
        warnings.append("Partial credit is set but status is not partially_implemented")
    return warnings


# --------------------------------------------------------------------------------------------
# Validation shared by PUT and bulk POST
# --------------------------------------------------------------------------------------------
def apply_implementation_changes(
    session: Session, impl: ControlImplementation, changes: dict[str, Any], actor: str
) -> list[str]:
    """Validate and apply a partial update; returns the list of changed field names.

    Rules: ``provider_id`` must exist; ``partial_credit`` other than ``none`` is only valid on
    3.5.3 (``mfa_partial``) / 3.13.11 (``encryption_non_fips``) and requires status
    ``partially_implemented``; leaving ``partially_implemented`` resets partial credit.
    """
    if "provider_id" in changes and changes["provider_id"] is not None:
        if session.get(Provider, changes["provider_id"]) is None:
            raise bad_request(f"Unknown provider id {changes['provider_id']}")

    new_status = ImplementationStatus(changes.get("status", impl.status))
    explicit_partial = "partial_credit" in changes and changes["partial_credit"] is not None
    new_partial = (
        PartialCredit(changes["partial_credit"]) if explicit_partial else PartialCredit(impl.partial_credit)
    )

    if explicit_partial and new_partial != PartialCredit.none:
        allowed = PARTIAL_CREDIT_CONTROLS.get(impl.control_id)
        if allowed is None:
            raise bad_request(
                f"partial_credit is only valid for controls {', '.join(PARTIAL_CREDIT_CONTROLS)}; "
                f"{impl.control_id} has no partial-credit rule"
            )
        if allowed != new_partial:
            raise bad_request(
                f"partial_credit '{new_partial.value}' is not valid for {impl.control_id}; "
                f"use '{allowed.value}'"
            )
        if new_status != ImplementationStatus.partially_implemented:
            raise bad_request("partial_credit requires status 'partially_implemented'")
    elif not explicit_partial and new_status != ImplementationStatus.partially_implemented:
        if PartialCredit(impl.partial_credit) != PartialCredit.none:
            changes["partial_credit"] = PartialCredit.none

    changed: list[str] = []
    status_changed = new_status != ImplementationStatus(impl.status)
    for key, value in changes.items():
        if key == "partial_credit" and value is None:
            continue
        if getattr(impl, key) != value:
            setattr(impl, key, value)
            changed.append(key)
    if status_changed:
        if "assessed_at" not in changes or changes["assessed_at"] is None:
            impl.assessed_at = utcnow()
        if not (changes.get("assessed_by") or impl.assessed_by):
            impl.assessed_by = actor
    if changed:
        impl.touch()
        session.add(impl)
    return changed


def _catalog_objectives(control: dict[str, Any]) -> list[dict[str, Any]]:
    return list(control.get("objectives", []))


def _objective_reads(control: dict[str, Any], rows: list[ObjectiveAssessment]) -> list[ObjectiveRead]:
    by_id = {row.objective_id: row for row in rows}
    out: list[ObjectiveRead] = []
    for objective in _catalog_objectives(control):
        row = by_id.get(objective["id"])
        out.append(
            ObjectiveRead(
                id=row.id if row else None,
                objective_id=objective["id"],
                letter=objective.get("letter"),
                text=objective.get("text", ""),
                status=row.status if row else ObjectiveStatus.unknown,
                notes=row.notes if row else None,
                updated_at=row.updated_at if row else None,
            )
        )
    return out


def _counts_from_rows(rows: list[ObjectiveAssessment]) -> ObjectiveCounts:
    counts = ObjectiveCounts(total=len(rows))
    for row in rows:
        key = ObjectiveStatus(row.status).value
        setattr(counts, key, getattr(counts, key) + 1)
    return counts


# --------------------------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------------------------
@router.get("", response_model=list[ControlListItem])
def list_controls(system_id: int, session: SessionDep) -> list[ControlListItem]:
    """110 rows in catalog order: catalog summary, implementation, objective counts, evidence and
    POA&M counts and a summary of the latest agent checks."""
    system = get_system_or_404(session, system_id)
    impls = {
        impl.control_id: impl
        for impl in session.exec(
            select(ControlImplementation).where(ControlImplementation.system_id == system_id)
        ).all()
    }
    if len(impls) < len(catalog.control_ids()):
        seed_implementations(session, system)
        session.commit()
        impls = {
            impl.control_id: impl
            for impl in session.exec(
                select(ControlImplementation).where(ControlImplementation.system_id == system_id)
            ).all()
        }
    objective_counts = _objective_counts(session, system_id)
    evidence_counts = _evidence_counts(session, system_id)
    poam_counts = _open_poam_counts(session, system_id)
    checks_by_control = _results_by_control(_latest_results(session, system_id))

    items: list[ControlListItem] = []
    for summary in catalog.controls_summary():
        impl = impls.get(summary["id"])
        if impl is None:
            continue
        counts = objective_counts.get(impl.id, ObjectiveCounts(total=summary.get("objective_count", 0)))
        items.append(
            ControlListItem(
                control=summary,
                implementation=ImplementationRead.model_validate(impl),
                objective_counts=counts,
                evidence_count=evidence_counts.get(summary["id"], 0),
                check_summary=_summarise(checks_by_control.get(summary["id"], [])),
                open_poam_count=poam_counts.get(summary["id"], 0),
                warnings=implementation_warnings(impl, counts),
            )
        )
    return items


@router.post("/bulk", response_model=BulkControlResponse)
def bulk_update(
    system_id: int, body: list[BulkControlItem], session: SessionDep, actor: ActorDep
) -> BulkControlResponse:
    """Set status / responsibility / provider on many controls at once."""
    get_system_or_404(session, system_id)
    unknown = sorted({item.control_id for item in body if catalog.control(item.control_id) is None})
    if unknown:
        raise bad_request(f"Unknown control ids: {', '.join(unknown)}")
    updated: list[ControlImplementation] = []
    for item in body:
        impl = ensure_implementation(session, system_id, item.control_id)
        changes = item.model_dump(exclude_unset=True, exclude={"control_id"})
        if apply_implementation_changes(session, impl, changes, actor):
            updated.append(impl)
    log_activity(
        session,
        actor,
        "bulk_update",
        "control_implementation",
        None,
        f"Bulk-updated {len(updated)} of {len(body)} control(s)",
        system_id=system_id,
    )
    session.commit()
    for impl in updated:
        session.refresh(impl)
    return BulkControlResponse(
        updated=len(updated), implementations=[ImplementationRead.model_validate(i) for i in updated]
    )


@router.get("/{control_id}", response_model=ControlDetail)
def read_control(system_id: int, control_id: str, session: SessionDep) -> ControlDetail:
    """Catalog control + implementation + objectives with statuses + evidence + checks + POA&M."""
    get_system_or_404(session, system_id)
    control = require_catalog_control(control_id)
    impl = ensure_implementation(session, system_id, control_id)
    session.commit()
    return _detail(session, system_id, control, impl)


def _detail(
    session: Session, system_id: int, control: dict[str, Any], impl: ControlImplementation
) -> ControlDetail:
    control_id = control["id"]
    objective_rows = list(
        session.exec(
            select(ObjectiveAssessment).where(ObjectiveAssessment.implementation_id == impl.id)
        ).all()
    )
    counts = _counts_from_rows(objective_rows)

    evidence_rows = list(
        session.exec(
            select(Evidence)
            .join(EvidenceLink, EvidenceLink.evidence_id == Evidence.id)
            .where(Evidence.system_id == system_id, EvidenceLink.control_id == control_id)
            .distinct()
            .order_by(Evidence.collected_at.desc(), Evidence.id.desc())
        ).all()
    )
    links = links_by_evidence(session, [e.id for e in evidence_rows if e.id is not None])

    results = [
        r for r in _latest_results(session, system_id) if control_id in json.loads(r.control_ids_json or "[]")
    ]

    poam_rows = list(
        session.exec(
            select(PoamItem)
            .where(PoamItem.system_id == system_id, PoamItem.control_id == control_id)
            .order_by(PoamItem.created_at.desc(), PoamItem.id.desc())
        ).all()
    )
    milestones = milestones_by_item(session, [p.id for p in poam_rows if p.id is not None])

    provider = session.get(Provider, impl.provider_id) if impl.provider_id is not None else None
    responsibility_row = None
    if provider is not None:
        row = session.exec(
            select(ResponsibilityRow).where(
                ResponsibilityRow.provider_id == provider.id, ResponsibilityRow.control_id == control_id
            )
        ).first()
        responsibility_row = matrix_row_read(provider.id, control, row)

    full = {
        **control,
        **(catalog.control_summary(control_id) or {}),
        "objectives": control.get("objectives", []),
    }
    return ControlDetail(
        control=full,
        implementation=ImplementationRead.model_validate(impl),
        provider=provider,
        responsibility_row=responsibility_row,
        objectives=_objective_reads(control, objective_rows),
        objective_counts=counts,
        evidence=[to_evidence_read(e, links.get(e.id, [])) for e in evidence_rows],
        check_results=[to_check_result_read(r) for r in results],
        check_summary=_summarise(results),
        poam_items=[to_poam_read(p, milestones.get(p.id, [])) for p in poam_rows],
        open_poam_count=sum(1 for p in poam_rows if p.status in OPEN_POAM_STATUSES),
        warnings=implementation_warnings(impl, counts),
    )


@router.put("/{control_id}", response_model=ControlDetail)
def update_control(
    system_id: int, control_id: str, body: ImplementationUpdate, session: SessionDep, actor: ActorDep
) -> ControlDetail:
    """Partial update of the implementation record (only fields present in the body change)."""
    get_system_or_404(session, system_id)
    control = require_catalog_control(control_id)
    impl = ensure_implementation(session, system_id, control_id)
    changes = body.model_dump(exclude_unset=True)
    changed = apply_implementation_changes(session, impl, changes, actor)
    log_activity(
        session,
        actor,
        "update",
        "control_implementation",
        impl.id,
        f"Updated control {control_id} ({', '.join(changed) or 'no changes'}); status={impl.status}",
        system_id=system_id,
    )
    session.commit()
    session.refresh(impl)
    return _detail(session, system_id, control, impl)


@router.put("/{control_id}/objectives", response_model=list[ObjectiveRead])
def update_objectives(
    system_id: int, control_id: str, body: list[ObjectiveUpdateItem], session: SessionDep, actor: ActorDep
) -> list[ObjectiveRead]:
    """Bulk upsert of objective statuses for a control; returns every objective with its status."""
    get_system_or_404(session, system_id)
    control = require_catalog_control(control_id)
    valid_ids = {o["id"] for o in _catalog_objectives(control)}
    unknown = sorted({item.objective_id for item in body if item.objective_id not in valid_ids})
    if unknown:
        raise bad_request(f"Objective ids not part of {control_id}: {', '.join(unknown)}")
    impl = ensure_implementation(session, system_id, control_id)
    rows = {
        row.objective_id: row
        for row in session.exec(
            select(ObjectiveAssessment).where(ObjectiveAssessment.implementation_id == impl.id)
        ).all()
    }
    changed = 0
    for item in body:
        row = rows.get(item.objective_id)
        if row is None:
            row = ObjectiveAssessment(implementation_id=impl.id, objective_id=item.objective_id)
            rows[item.objective_id] = row
        new_status = ObjectiveStatus(item.status)
        if row.status != new_status or row.notes != item.notes:
            row.status = new_status
            row.notes = item.notes
            row.touch()
            session.add(row)
            changed += 1
    log_activity(
        session,
        actor,
        "update",
        "objective_assessment",
        impl.id,
        f"Updated {changed} objective(s) of control {control_id}",
        system_id=system_id,
    )
    session.commit()
    rows_after = list(
        session.exec(
            select(ObjectiveAssessment).where(ObjectiveAssessment.implementation_id == impl.id)
        ).all()
    )
    return _objective_reads(control, rows_after)


__all__ = ["router", "apply_implementation_changes", "implementation_warnings", "get_implementation"]
