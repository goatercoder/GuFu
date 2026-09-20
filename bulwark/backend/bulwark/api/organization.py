"""``/api/organization``: the single organization for this install."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..activity import log_activity
from ..auth import require_admin
from ..models import Organization
from ..schemas import OrganizationRead, OrganizationUpsert
from .deps import ActorDep, SessionDep, get_organization, not_found

router = APIRouter(prefix="/organization", tags=["organization"], dependencies=[Depends(require_admin)])


@router.get("", response_model=OrganizationRead)
def read_organization(session: SessionDep) -> Organization:
    org = get_organization(session)
    if org is None:
        raise not_found("Organization", "(not created yet)")
    return org


@router.put("", response_model=OrganizationRead)
def upsert_organization(body: OrganizationUpsert, session: SessionDep, actor: ActorDep) -> Organization:
    """Create the organization on first call; afterwards update the fields present in the body."""
    org = get_organization(session)
    changes = body.model_dump(exclude_unset=True)
    if org is None:
        org = Organization(**changes)
        session.add(org)
        session.flush()
        log_activity(session, actor, "create", "organization", org.id, f"Created organization '{org.name}'")
    else:
        for key, value in changes.items():
            setattr(org, key, value)
        org.touch()
        session.add(org)
        log_activity(session, actor, "update", "organization", org.id, f"Updated organization '{org.name}'")
    session.commit()
    session.refresh(org)
    return org
