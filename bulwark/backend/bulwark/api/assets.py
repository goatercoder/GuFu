"""``/api/systems/{id}/assets`` and ``/api/assets/{id}``: the asset inventory."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import or_
from sqlmodel import select

from ..activity import log_activity
from ..auth import require_admin
from ..models import AgentReport, Asset, AssetCategory, AssetType, CheckResult
from ..schemas import AgentReportRead, AssetCreate, AssetRead, AssetUpdate, CheckResultRead, OkResponse
from ..services import delete_asset_cascade
from .deps import ActorDep, SessionDep, get_asset_or_404, get_system_or_404, to_check_result_read

router = APIRouter(tags=["assets"], dependencies=[Depends(require_admin)])


@router.get("/systems/{system_id}/assets", response_model=list[AssetRead])
def list_assets(
    system_id: int,
    session: SessionDep,
    category: Annotated[AssetCategory | None, Query()] = None,
    type: Annotated[AssetType | None, Query(alias="type")] = None,  # noqa: A002
    q: Annotated[str | None, Query(max_length=200)] = None,
) -> list[Asset]:
    """Assets of a system, filterable by CMMC category, asset type and a free-text ``q``."""
    get_system_or_404(session, system_id)
    stmt = select(Asset).where(Asset.system_id == system_id)
    if category is not None:
        stmt = stmt.where(Asset.category == category)
    if type is not None:
        stmt = stmt.where(Asset.asset_type == type)
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Asset.name.ilike(pattern),
                Asset.ip_address.ilike(pattern),
                Asset.os_name.ilike(pattern),
                Asset.owner.ilike(pattern),
                Asset.location.ilike(pattern),
                Asset.serial_number.ilike(pattern),
                Asset.description.ilike(pattern),
            )
        )
    return list(session.exec(stmt.order_by(Asset.name, Asset.id)).all())


@router.post("/systems/{system_id}/assets", response_model=AssetRead, status_code=status.HTTP_201_CREATED)
def create_asset(system_id: int, body: AssetCreate, session: SessionDep, actor: ActorDep) -> Asset:
    get_system_or_404(session, system_id)
    asset = Asset(system_id=system_id, **body.model_dump())
    session.add(asset)
    session.flush()
    log_activity(
        session, actor, "create", "asset", asset.id, f"Added asset '{asset.name}'", system_id=system_id
    )
    session.commit()
    session.refresh(asset)
    return asset


@router.get("/assets/{asset_id}", response_model=AssetRead)
def read_asset(asset_id: int, session: SessionDep) -> Asset:
    return get_asset_or_404(session, asset_id)


@router.put("/assets/{asset_id}", response_model=AssetRead)
def update_asset(asset_id: int, body: AssetUpdate, session: SessionDep, actor: ActorDep) -> Asset:
    asset = get_asset_or_404(session, asset_id)
    changes = body.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(asset, key, value)
    asset.touch()
    session.add(asset)
    log_activity(
        session,
        actor,
        "update",
        "asset",
        asset.id,
        f"Updated asset '{asset.name}' ({', '.join(sorted(changes)) or 'no changes'})",
        system_id=asset.system_id,
    )
    session.commit()
    session.refresh(asset)
    return asset


@router.delete("/assets/{asset_id}", response_model=OkResponse)
def delete_asset(asset_id: int, session: SessionDep, actor: ActorDep) -> OkResponse:
    asset = get_asset_or_404(session, asset_id)
    name, system_id = asset.name, asset.system_id
    delete_asset_cascade(session, asset)
    log_activity(session, actor, "delete", "asset", asset_id, f"Deleted asset '{name}'", system_id=system_id)
    session.commit()
    return OkResponse()


@router.get("/assets/{asset_id}/checks", response_model=list[CheckResultRead])
def asset_checks(asset_id: int, session: SessionDep) -> list[CheckResultRead]:
    """Latest result for every check the asset's agent has reported."""
    get_asset_or_404(session, asset_id)
    rows = session.exec(
        select(CheckResult)
        .where(CheckResult.asset_id == asset_id, CheckResult.is_latest == True)  # noqa: E712
        .order_by(CheckResult.check_id)
    ).all()
    return [to_check_result_read(row) for row in rows]


@router.get("/assets/{asset_id}/reports", response_model=list[AgentReportRead])
def asset_reports(asset_id: int, session: SessionDep) -> list[AgentReport]:
    """Report history for the asset, newest first (never includes raw JSON)."""
    get_asset_or_404(session, asset_id)
    return list(
        session.exec(
            select(AgentReport)
            .where(AgentReport.asset_id == asset_id)
            .order_by(AgentReport.received_at.desc(), AgentReport.id.desc())
        ).all()
    )
