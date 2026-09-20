"""Administrative helpers: demo data and the activity log."""

from __future__ import annotations

from fastapi import APIRouter, Query
from sqlmodel import select

from ..models import ActivityLog
from ..schemas import ActivityRead
from ..seed import seed_demo
from .deps import ActorDep, SessionDep

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/seed-demo")
def post_seed_demo(session: SessionDep, actor: ActorDep) -> dict:
    """Load the demo machine shop so the product can be evaluated with real data."""
    return seed_demo(session, actor=actor)


@router.get("/activity", response_model=list[ActivityRead])
def read_activity(
    session: SessionDep,
    actor: ActorDep,
    system_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[ActivityRead]:
    """Recent changes, newest first: who did what, and to which record."""
    query = select(ActivityLog).order_by(ActivityLog.id.desc()).limit(limit)  # type: ignore[union-attr]
    if system_id is not None:
        query = query.where(ActivityLog.system_id == system_id)
    return [ActivityRead.model_validate(row) for row in session.exec(query).all()]
