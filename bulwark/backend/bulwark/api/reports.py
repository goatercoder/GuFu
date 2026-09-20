"""Document exports: system security plan, POA&M and the readiness report."""

from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from sqlmodel import select

from ..evidence_rules import findings_for_system
from ..models import Organization, System
from ..reports import markdown_to_docx, poam_csv, poam_markdown, readiness_markdown
from ..ssp import build_context, render_docx, render_html, render_markdown
from ..ssp.render import INLINE_TEMPLATE
from .deps import ActorDep, SessionDep, get_system_or_404
from .scoring import readiness as compute_readiness

router = APIRouter(prefix="/systems/{system_id}", tags=["reports"])

DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

SspFormat = Literal["md", "html", "docx", "json"]
PoamFormat = Literal["csv", "md", "docx"]
ReportFormat = Literal["md", "html", "docx"]


def _slug(text: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in text.strip().lower())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "system"


def _attachment(filename: str) -> dict[str, str]:
    return {"Content-Disposition": f'attachment; filename="{filename}"'}


def _organization_name(session) -> str:
    org = session.exec(select(Organization).order_by(Organization.id)).first()
    return org.name if org else "Organization"


@router.get("/ssp")
def export_ssp(
    system_id: int,
    session: SessionDep,
    actor: ActorDep,
    format: SspFormat = Query(default="md"),
) -> Response:
    """The system security plan, generated from the live record."""
    system: System = get_system_or_404(session, system_id)
    context = build_context(session, system)
    stem = f"ssp-{_slug(system.name)}-{context['generated_date']}"

    if format == "json":
        return Response(
            content=json.dumps(context, indent=2, default=str),
            media_type="application/json",
            headers=_attachment(f"{stem}.json"),
        )
    if format == "html":
        return HTMLResponse(content=render_html(context))
    if format == "docx":
        return Response(
            content=render_docx(context),
            media_type=DOCX_MEDIA_TYPE,
            headers=_attachment(f"{stem}.docx"),
        )
    return PlainTextResponse(
        content=render_markdown(context),
        media_type="text/markdown; charset=utf-8",
        headers=_attachment(f"{stem}.md"),
    )


@router.get("/poam/export")
def export_poam(
    system_id: int,
    session: SessionDep,
    actor: ActorDep,
    format: PoamFormat = Query(default="csv"),
) -> Response:
    """The plan of action and milestones in the columns assessors expect."""
    system: System = get_system_or_404(session, system_id)
    stem = f"poam-{_slug(system.name)}"
    if format == "csv":
        return PlainTextResponse(
            content=poam_csv(session, system),
            media_type="text/csv; charset=utf-8",
            headers=_attachment(f"{stem}.csv"),
        )
    markdown = poam_markdown(session, system, _organization_name(session))
    if format == "docx":
        return Response(
            content=markdown_to_docx(markdown),
            media_type=DOCX_MEDIA_TYPE,
            headers=_attachment(f"{stem}.docx"),
        )
    return PlainTextResponse(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers=_attachment(f"{stem}.md"),
    )


@router.get("/readiness-report")
def export_readiness_report(
    system_id: int,
    session: SessionDep,
    actor: ActorDep,
    format: ReportFormat = Query(default="md"),
) -> Response:
    """A short readiness briefing for the owner: score, blockers and next actions."""
    system: System = get_system_or_404(session, system_id)
    ssp_context = build_context(session, system)
    context = {
        "generated_at": ssp_context["generated_at"],
        "organization": ssp_context["organization"],
        "system": ssp_context["system"],
        "score": ssp_context["score"],
        "readiness": compute_readiness(session, system_id),
        "findings": findings_for_system(session, system_id),
    }
    markdown = readiness_markdown(context)
    stem = f"readiness-{_slug(system.name)}-{ssp_context['generated_date']}"
    if format == "html":
        return HTMLResponse(
            content=render_html(
                {"_markdown": markdown},
                title=f"Assessment readiness - {system.name}",
                template=INLINE_TEMPLATE,
            )
        )
    if format == "docx":
        return Response(
            content=markdown_to_docx(markdown),
            media_type=DOCX_MEDIA_TYPE,
            headers=_attachment(f"{stem}.docx"),
        )
    return PlainTextResponse(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers=_attachment(f"{stem}.md"),
    )
