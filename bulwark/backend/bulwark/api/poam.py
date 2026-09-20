"""POA&M items, milestones and the remediation workflow.

The status workflow (ARCHITECTURE.md §4.3) is deliberately strict: an assessor reading the
history should be able to see how a weakness moved from identified to closed.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query, status
from sqlmodel import select

from ..activity import log_activity
from ..evidence_rules import risk_for_weight
from ..models import (
    PoamItem,
    PoamMilestone,
    PoamStatus,
    utcnow,
)
from ..schemas import (
    OkResponse,
    PoamItemCreate,
    PoamItemRead,
    PoamItemUpdate,
    PoamMilestoneCreate,
    PoamMilestoneRead,
    PoamMilestoneUpdate,
    PoamTransitionRequest,
)
from .deps import (
    ActorDep,
    SessionDep,
    bad_request,
    get_system_or_404,
    milestones_by_item,
    not_found,
    require_catalog_control,
    to_poam_read,
)

router = APIRouter(tags=["poam"])

#: status -> statuses it may move to.
TRANSITIONS: dict[PoamStatus, set[PoamStatus]] = {
    PoamStatus.open: {PoamStatus.in_progress, PoamStatus.completed, PoamStatus.risk_accepted},
    PoamStatus.in_progress: {PoamStatus.open, PoamStatus.completed, PoamStatus.risk_accepted},
    PoamStatus.completed: {PoamStatus.closed, PoamStatus.in_progress},
    PoamStatus.risk_accepted: {PoamStatus.closed, PoamStatus.open, PoamStatus.in_progress},
    PoamStatus.closed: {PoamStatus.open},
}


def _get_item(session, item_id: int) -> PoamItem:
    item = session.get(PoamItem, item_id)
    if item is None:
        raise not_found("POA&M item", item_id)
    return item


def _read(session, item: PoamItem) -> PoamItemRead:
    milestones = session.exec(
        select(PoamMilestone).where(PoamMilestone.poam_item_id == item.id)
    ).all()
    return to_poam_read(item, list(milestones))


def _status(item: PoamItem) -> PoamStatus:
    """SQLite hands enum columns back as plain strings; normalise before comparing."""
    return item.status if isinstance(item.status, PoamStatus) else PoamStatus(str(item.status))


def _append_note(item: PoamItem, note: str) -> None:
    stamp = utcnow().strftime("%Y-%m-%d %H:%M UTC")
    line = f"[{stamp}] {note}"
    item.notes = f"{item.notes}\n{line}" if item.notes else line


# --------------------------------------------------------------------------------------------
# Items
# --------------------------------------------------------------------------------------------
@router.get("/systems/{system_id}/poam", response_model=list[PoamItemRead])
def list_items(
    system_id: int,
    session: SessionDep,
    actor: ActorDep,
    status_filter: PoamStatus | None = Query(default=None, alias="status"),
    control_id: str | None = Query(default=None),
    overdue: bool | None = Query(default=None),
) -> list[PoamItemRead]:
    """POA&M register for a system, newest first, with milestones."""
    get_system_or_404(session, system_id)
    query = select(PoamItem).where(PoamItem.system_id == system_id)
    if status_filter is not None:
        query = query.where(PoamItem.status == status_filter)
    if control_id:
        query = query.where(PoamItem.control_id == control_id)
    items = list(session.exec(query).all())
    if overdue is not None:
        today = date.today()

        def is_overdue(item: PoamItem) -> bool:
            return (
                item.scheduled_completion is not None
                and item.scheduled_completion < today
                and _status(item) in (PoamStatus.open, PoamStatus.in_progress)
            )

        items = [item for item in items if is_overdue(item) == overdue]
    items.sort(key=lambda i: (_status(i) != PoamStatus.open, -(i.id or 0)))
    by_item = milestones_by_item(session, [i.id for i in items if i.id is not None])
    return [to_poam_read(item, by_item.get(item.id, [])) for item in items]


@router.post("/systems/{system_id}/poam", response_model=PoamItemRead, status_code=status.HTTP_201_CREATED)
def create_item(
    system_id: int, payload: PoamItemCreate, session: SessionDep, actor: ActorDep
) -> PoamItemRead:
    """Record a weakness. Risk defaults to the requirement's DoD point value."""
    system = get_system_or_404(session, system_id)
    control = require_catalog_control(payload.control_id)
    item = PoamItem(
        system_id=system.id,
        control_id=payload.control_id,
        title=payload.title,
        weakness_description=payload.weakness_description,
        source=payload.source,
        risk_level=payload.risk_level or risk_for_weight(control.get("weight", 1)),
        status=PoamStatus.open,
        owner=payload.owner,
        identified_at=payload.identified_at or date.today(),
        scheduled_completion=payload.scheduled_completion,
        remediation_plan=payload.remediation_plan,
        resources_required=payload.resources_required,
        cost_estimate=payload.cost_estimate,
        check_id=payload.check_id,
        asset_id=payload.asset_id,
        notes=payload.notes,
    )
    session.add(item)
    session.flush()
    for position, milestone in enumerate(payload.milestones):
        session.add(
            PoamMilestone(
                poam_item_id=item.id,
                description=milestone.description,
                due_date=milestone.due_date,
                completed_at=milestone.completed_at,
                position=milestone.position if milestone.position is not None else position,
            )
        )
    log_activity(
        session,
        actor,
        "create",
        "poam_item",
        item.id,
        f"Opened POA&M item for {payload.control_id}: {payload.title}",
        system_id=system.id,
    )
    session.commit()
    session.refresh(item)
    return _read(session, item)


@router.get("/poam/{item_id}", response_model=PoamItemRead)
def read_item(item_id: int, session: SessionDep, actor: ActorDep) -> PoamItemRead:
    return _read(session, _get_item(session, item_id))


@router.put("/poam/{item_id}", response_model=PoamItemRead)
def update_item(
    item_id: int, payload: PoamItemUpdate, session: SessionDep, actor: ActorDep
) -> PoamItemRead:
    """Edit the fields of an item. Use ``/transition`` to change its status."""
    item = _get_item(session, item_id)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(item, field, value)
    if changes:
        item.updated_at = utcnow()
        session.add(item)
        log_activity(
            session,
            actor,
            "update",
            "poam_item",
            item.id,
            f"Updated {', '.join(sorted(changes))} on POA&M item {item.id}",
            system_id=item.system_id,
        )
        session.commit()
        session.refresh(item)
    return _read(session, item)


@router.delete("/poam/{item_id}", response_model=OkResponse)
def delete_item(item_id: int, session: SessionDep, actor: ActorDep) -> OkResponse:
    item = _get_item(session, item_id)
    for milestone in session.exec(
        select(PoamMilestone).where(PoamMilestone.poam_item_id == item.id)
    ).all():
        session.delete(milestone)
    session.flush()
    system_id = item.system_id
    title = item.title
    session.delete(item)
    log_activity(session, actor, "delete", "poam_item", item_id, f"Deleted POA&M item: {title}",
                 system_id=system_id)
    session.commit()
    return OkResponse()


@router.post("/poam/{item_id}/transition", response_model=PoamItemRead)
def transition(
    item_id: int, payload: PoamTransitionRequest, session: SessionDep, actor: ActorDep
) -> PoamItemRead:
    """Move an item through the workflow, recording who moved it and why."""
    item = _get_item(session, item_id)
    target = payload.status if isinstance(payload.status, PoamStatus) else PoamStatus(str(payload.status))
    previous = _status(item)
    if target == previous:
        raise bad_request(f"POA&M item {item_id} is already {target.value}")
    allowed = TRANSITIONS.get(previous, set())
    if target not in allowed:
        allowed_text = ", ".join(sorted(s.value for s in allowed)) or "no further transitions"
        article = "an" if previous.value[0] in "aeiou" else "a"
        raise bad_request(
            f"Cannot move {article} {previous.value} item to {target.value}; allowed: {allowed_text}"
        )
    item.status = target
    if target == PoamStatus.completed:
        item.actual_completion = item.actual_completion or date.today()
    if target in (PoamStatus.open, PoamStatus.in_progress):
        item.actual_completion = None
    note = f"Status {previous.value} -> {target.value}" + (f": {payload.note}" if payload.note else "")
    _append_note(item, note)
    item.updated_at = utcnow()
    session.add(item)
    log_activity(session, actor, "transition", "poam_item", item.id, note, system_id=item.system_id)
    session.commit()
    session.refresh(item)
    return _read(session, item)


# --------------------------------------------------------------------------------------------
# Milestones
# --------------------------------------------------------------------------------------------
@router.post(
    "/poam/{item_id}/milestones", response_model=PoamMilestoneRead, status_code=status.HTTP_201_CREATED
)
def add_milestone(
    item_id: int, payload: PoamMilestoneCreate, session: SessionDep, actor: ActorDep
) -> PoamMilestoneRead:
    item = _get_item(session, item_id)
    existing = session.exec(select(PoamMilestone).where(PoamMilestone.poam_item_id == item.id)).all()
    milestone = PoamMilestone(
        poam_item_id=item.id,
        description=payload.description,
        due_date=payload.due_date,
        completed_at=payload.completed_at,
        position=payload.position if payload.position is not None else len(existing),
    )
    session.add(milestone)
    log_activity(
        session,
        actor,
        "create",
        "poam_milestone",
        None,
        f"Added milestone to POA&M item {item.id}: {payload.description}",
        system_id=item.system_id,
    )
    session.commit()
    session.refresh(milestone)
    return PoamMilestoneRead.model_validate(milestone)


@router.put("/milestones/{milestone_id}", response_model=PoamMilestoneRead)
def update_milestone(
    milestone_id: int, payload: PoamMilestoneUpdate, session: SessionDep, actor: ActorDep
) -> PoamMilestoneRead:
    milestone = session.get(PoamMilestone, milestone_id)
    if milestone is None:
        raise not_found("Milestone", milestone_id)
    changes = payload.model_dump(exclude_unset=True)
    completed = changes.pop("completed", None)
    for field, value in changes.items():
        setattr(milestone, field, value)
    if completed is True:
        milestone.completed_at = milestone.completed_at or utcnow()
    elif completed is False:
        milestone.completed_at = None
    milestone.updated_at = utcnow()
    session.add(milestone)
    item = session.get(PoamItem, milestone.poam_item_id)
    log_activity(
        session,
        actor,
        "update",
        "poam_milestone",
        milestone.id,
        f"Updated milestone on POA&M item {milestone.poam_item_id}",
        system_id=item.system_id if item else None,
    )
    session.commit()
    session.refresh(milestone)
    return PoamMilestoneRead.model_validate(milestone)


@router.delete("/milestones/{milestone_id}", response_model=OkResponse)
def delete_milestone(milestone_id: int, session: SessionDep, actor: ActorDep) -> OkResponse:
    milestone = session.get(PoamMilestone, milestone_id)
    if milestone is None:
        raise not_found("Milestone", milestone_id)
    item = session.get(PoamItem, milestone.poam_item_id)
    session.delete(milestone)
    log_activity(
        session,
        actor,
        "delete",
        "poam_milestone",
        milestone_id,
        f"Deleted milestone from POA&M item {milestone.poam_item_id}",
        system_id=item.system_id if item else None,
    )
    session.commit()
    return OkResponse()
