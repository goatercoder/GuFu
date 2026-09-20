"""``/api/providers``: external service providers and their shared-responsibility matrix."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, status
from sqlmodel import Session, select

from .. import catalog
from ..activity import log_activity
from ..auth import require_admin
from ..models import Provider, ResponsibilityModel, ResponsibilityRow
from ..schemas import (
    ApplyTemplateRequest,
    ApplyTemplateResponse,
    OkResponse,
    ProviderCreate,
    ProviderRead,
    ProviderUpdate,
    ResponsibilityRowIn,
    ResponsibilityRowRead,
)
from ..services import delete_provider_cascade
from .deps import ActorDep, SessionDep, bad_request, get_provider_or_404, not_found, require_organization

router = APIRouter(prefix="/providers", tags=["providers"], dependencies=[Depends(require_admin)])


# --------------------------------------------------------------------------------------------
# Matrix helpers (reused by the controls router)
# --------------------------------------------------------------------------------------------
def matrix_row_read(
    provider_id: int, control: dict[str, Any], row: ResponsibilityRow | None
) -> ResponsibilityRowRead:
    base = {
        "provider_id": provider_id,
        "control_id": control["id"],
        "control_name": control.get("name") or "",
        "cmmc_id": control.get("cmmc_id"),
        "family_id": control.get("family_id"),
        "family_abbr": control.get("family_abbr"),
        "weight": control.get("weight", 0),
    }
    if row is None:
        return ResponsibilityRowRead(**base)
    return ResponsibilityRowRead(
        **base,
        id=row.id,
        model=row.model,
        provider_responsibility=row.provider_responsibility,
        customer_responsibility=row.customer_responsibility,
        inherited=row.inherited,
        updated_at=row.updated_at,
    )


def stored_rows(session: Session, provider_id: int) -> dict[str, ResponsibilityRow]:
    rows = session.exec(select(ResponsibilityRow).where(ResponsibilityRow.provider_id == provider_id)).all()
    return {row.control_id: row for row in rows}


def full_matrix(session: Session, provider_id: int) -> list[ResponsibilityRowRead]:
    """One row per catalog control in catalog order; missing rows read as ``not_covered``."""
    rows = stored_rows(session, provider_id)
    return [matrix_row_read(provider_id, ctrl, rows.get(ctrl["id"])) for ctrl in catalog.controls()]


def upsert_rows(session: Session, provider_id: int, items: list[ResponsibilityRowIn]) -> int:
    """Insert-or-update rows; returns the number of rows touched."""
    rows = stored_rows(session, provider_id)
    touched = 0
    for item in items:
        row = rows.get(item.control_id)
        if row is None:
            row = ResponsibilityRow(provider_id=provider_id, control_id=item.control_id)
            rows[item.control_id] = row
        row.model = ResponsibilityModel(item.model)
        row.provider_responsibility = item.provider_responsibility
        row.customer_responsibility = item.customer_responsibility
        row.inherited = item.inherited
        row.touch()
        session.add(row)
        touched += 1
    session.flush()
    return touched


# --------------------------------------------------------------------------------------------
# Provider CRUD
# --------------------------------------------------------------------------------------------
@router.get("", response_model=list[ProviderRead])
def list_providers(session: SessionDep) -> list[Provider]:
    return list(session.exec(select(Provider).order_by(Provider.name, Provider.id)).all())


@router.post("", response_model=ProviderRead, status_code=status.HTTP_201_CREATED)
def create_provider(body: ProviderCreate, session: SessionDep, actor: ActorDep) -> Provider:
    org = require_organization(session)
    provider = Provider(organization_id=org.id, **body.model_dump())
    session.add(provider)
    session.flush()
    log_activity(session, actor, "create", "provider", provider.id, f"Added provider '{provider.name}'")
    session.commit()
    session.refresh(provider)
    return provider


@router.get("/{provider_id}", response_model=ProviderRead)
def read_provider(provider_id: int, session: SessionDep) -> Provider:
    return get_provider_or_404(session, provider_id)


@router.put("/{provider_id}", response_model=ProviderRead)
def update_provider(provider_id: int, body: ProviderUpdate, session: SessionDep, actor: ActorDep) -> Provider:
    provider = get_provider_or_404(session, provider_id)
    changes = body.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(provider, key, value)
    provider.touch()
    session.add(provider)
    log_activity(
        session,
        actor,
        "update",
        "provider",
        provider.id,
        f"Updated provider '{provider.name}' ({', '.join(sorted(changes)) or 'no changes'})",
    )
    session.commit()
    session.refresh(provider)
    return provider


@router.delete("/{provider_id}", response_model=OkResponse)
def delete_provider(provider_id: int, session: SessionDep, actor: ActorDep) -> OkResponse:
    """Delete the provider and its matrix; implementations that referenced it lose the link."""
    provider = get_provider_or_404(session, provider_id)
    name = provider.name
    delete_provider_cascade(session, provider)
    log_activity(session, actor, "delete", "provider", provider_id, f"Deleted provider '{name}'")
    session.commit()
    return OkResponse()


# --------------------------------------------------------------------------------------------
# Shared-responsibility matrix
# --------------------------------------------------------------------------------------------
@router.get("/{provider_id}/matrix", response_model=list[ResponsibilityRowRead])
def read_matrix(provider_id: int, session: SessionDep) -> list[ResponsibilityRowRead]:
    get_provider_or_404(session, provider_id)
    return full_matrix(session, provider_id)


@router.put("/{provider_id}/matrix", response_model=list[ResponsibilityRowRead])
def put_matrix(
    provider_id: int, body: list[ResponsibilityRowIn], session: SessionDep, actor: ActorDep
) -> list[ResponsibilityRowRead]:
    """Bulk upsert rows; controls not in the body are left untouched."""
    provider = get_provider_or_404(session, provider_id)
    unknown = sorted({item.control_id for item in body if catalog.control(item.control_id) is None})
    if unknown:
        raise bad_request(f"Unknown control ids: {', '.join(unknown)}")
    touched = upsert_rows(session, provider_id, body)
    log_activity(
        session,
        actor,
        "update",
        "responsibility_matrix",
        provider_id,
        f"Updated {touched} responsibility row(s) for provider '{provider.name}'",
    )
    session.commit()
    return full_matrix(session, provider_id)


@router.post("/{provider_id}/matrix/apply-template", response_model=ApplyTemplateResponse)
def apply_template(
    provider_id: int, body: ApplyTemplateRequest, session: SessionDep, actor: ActorDep
) -> ApplyTemplateResponse:
    """Load ``catalog/enrichment/crm_templates/<template_id>.json`` and upsert its rows."""
    provider = get_provider_or_404(session, provider_id)
    template = catalog.load_crm_template(body.template_id)
    if template is None:
        raise not_found("CRM template", body.template_id)
    valid_models = {m.value for m in ResponsibilityModel}
    items: list[ResponsibilityRowIn] = []
    skipped: list[str] = []
    for raw in template.get("rows", []):
        if not isinstance(raw, dict):
            continue
        control_id = str(raw.get("control_id", ""))
        model = str(raw.get("model", "not_covered"))
        if catalog.control(control_id) is None or model not in valid_models:
            skipped.append(control_id or "?")
            continue
        items.append(
            ResponsibilityRowIn(
                control_id=control_id,
                model=model,
                provider_responsibility=raw.get("provider_responsibility"),
                customer_responsibility=raw.get("customer_responsibility"),
                inherited=bool(raw.get("inherited", False)),
            )
        )
    applied = upsert_rows(session, provider_id, items)
    log_activity(
        session,
        actor,
        "apply_template",
        "responsibility_matrix",
        provider_id,
        f"Applied CRM template '{template['id']}' to provider '{provider.name}' ({applied} rows)",
    )
    session.commit()
    return ApplyTemplateResponse(
        template_id=template["id"],
        template_name=template.get("name", template["id"]),
        applied=applied,
        skipped_control_ids=skipped,
        disclaimer=template.get("disclaimer"),
        rows=full_matrix(session, provider_id),
    )
