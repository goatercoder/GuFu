"""``/api/catalog/*``: read-only views of the built catalog."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from .. import catalog
from ..auth import require_admin
from ..schemas import CatalogCheck, CatalogControlFull, CatalogResponse, CrmTemplateSummary
from .deps import require_catalog_control

router = APIRouter(prefix="/catalog", tags=["catalog"], dependencies=[Depends(require_admin)])


@router.get("", response_model=CatalogResponse)
def get_catalog() -> CatalogResponse:
    """Families + control summaries (no discussion/assessment text) + check summaries."""
    return CatalogResponse(
        meta=catalog.meta(),
        families=catalog.families_summary(),
        controls=catalog.controls_summary(),
        checks=catalog.checks_summary(),
    )


@router.get("/checks", response_model=list[CatalogCheck])
def get_checks() -> list[dict]:
    return catalog.checks()


@router.get("/crm-templates", response_model=list[CrmTemplateSummary])
def get_crm_templates() -> list[dict]:
    """Available shared-responsibility templates; ``[]`` when the directory is empty or missing."""
    return catalog.list_crm_templates()


@router.get("/controls/{control_id}", response_model=CatalogControlFull)
def get_control(control_id: str) -> dict:
    """Full control record including discussion, objectives, assessment procedures and guidance."""
    ctrl = require_catalog_control(control_id)
    summary = catalog.control_summary(control_id) or {}
    return {**ctrl, **summary, "objectives": ctrl.get("objectives", [])}
