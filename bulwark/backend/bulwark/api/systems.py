"""``/api/systems``: assessment scopes. Creating a system seeds its 110 implementations."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlmodel import select

from ..activity import log_activity
from ..auth import require_admin
from ..models import System
from ..schemas import OkResponse, SystemCreate, SystemListItem, SystemRead, SystemUpdate
from ..services import asset_counts, delete_system_cascade, score_summaries, seed_implementations
from .deps import ActorDep, SessionDep, get_system_or_404, require_organization

router = APIRouter(prefix="/systems", tags=["systems"], dependencies=[Depends(require_admin)])


def _list_items(session, systems: list[System]) -> list[SystemListItem]:  # noqa: ANN001
    ids = [s.id for s in systems if s.id is not None]
    scores = score_summaries(session, ids)
    assets = asset_counts(session, ids)
    items: list[SystemListItem] = []
    for system in systems:
        base = SystemRead.model_validate(system).model_dump()
        items.append(
            SystemListItem(
                **base,
                score_summary=scores.get(system.id, {"met_count": 0, "total": 0}),
                asset_count=assets.get(system.id, 0),
            )
        )
    return items


def _item(session, system: System) -> SystemListItem:  # noqa: ANN001
    return _list_items(session, [system])[0]


@router.get("", response_model=list[SystemListItem])
def list_systems(session: SessionDep) -> list[SystemListItem]:
    """All systems with a lightweight ``score_summary`` (``{met_count, total}``)."""
    systems = session.exec(select(System).order_by(System.id)).all()
    return _list_items(session, list(systems))


@router.post("", response_model=SystemListItem, status_code=status.HTTP_201_CREATED)
def create_system(body: SystemCreate, session: SessionDep, actor: ActorDep) -> SystemListItem:
    """Create a system and seed 110 ``control_implementation`` + 320 ``objective_assessment`` rows."""
    org = require_organization(session)
    system = System(organization_id=org.id, **body.model_dump())
    session.add(system)
    session.flush()
    seeded = seed_implementations(session, system)
    log_activity(
        session,
        actor,
        "create",
        "system",
        system.id,
        f"Created system '{system.name}' ({seeded} control implementations seeded)",
        system_id=system.id,
    )
    session.commit()
    session.refresh(system)
    return _item(session, system)


@router.get("/{system_id}", response_model=SystemListItem)
def read_system(system_id: int, session: SessionDep) -> SystemListItem:
    return _item(session, get_system_or_404(session, system_id))


@router.put("/{system_id}", response_model=SystemListItem)
def update_system(system_id: int, body: SystemUpdate, session: SessionDep, actor: ActorDep) -> SystemListItem:
    system = get_system_or_404(session, system_id)
    changes = body.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(system, key, value)
    system.touch()
    session.add(system)
    log_activity(
        session,
        actor,
        "update",
        "system",
        system.id,
        f"Updated system '{system.name}' ({', '.join(sorted(changes)) or 'no changes'})",
        system_id=system.id,
    )
    session.commit()
    session.refresh(system)
    return _item(session, system)


@router.delete("/{system_id}", response_model=OkResponse)
def delete_system(system_id: int, session: SessionDep, actor: ActorDep) -> OkResponse:
    """Delete a system and everything it owns (assets, implementations, evidence, POA&M, reports)."""
    system = get_system_or_404(session, system_id)
    name = system.name
    delete_system_cascade(session, system)
    log_activity(session, actor, "delete", "system", system_id, f"Deleted system '{name}'")
    session.commit()
    return OkResponse()
