"""Evidence library: upload, link to requirements and objectives, download, expire."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlmodel import select

from .. import catalog
from ..activity import log_activity
from ..config import get_settings
from ..models import (
    Evidence,
    EvidenceKind,
    EvidenceLink,
    EvidenceSource,
    utcnow,
)
from ..schemas import (
    EvidenceLinkCreate,
    EvidenceLinkRead,
    EvidenceRead,
    EvidenceUpdate,
    OkResponse,
)
from .deps import (
    ActorDep,
    SessionDep,
    bad_request,
    get_system_or_404,
    is_expired,
    links_by_evidence,
    not_found,
    to_evidence_read,
)

router = APIRouter(tags=["evidence"])

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
MAX_NAME = 120


def safe_file_name(name: str | None) -> str:
    """Neutralise path traversal and odd characters; never trust a client file name."""
    base = Path(name or "evidence").name
    cleaned = _UNSAFE.sub("_", base).strip("._-") or "evidence"
    return cleaned[:MAX_NAME]


def _parse_ids(values: list[str] | None) -> list[str]:
    """Accept repeated form fields, a comma-separated string, or a JSON array."""
    out: list[str] = []
    for raw in values or []:
        text = (raw or "").strip()
        if not text:
            continue
        if text.startswith("["):
            try:
                out.extend(str(x) for x in json.loads(text))
                continue
            except ValueError:
                pass
        out.extend(part.strip() for part in text.split(",") if part.strip())
    seen: set[str] = set()
    unique = []
    for item in out:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def _link_targets(control_ids: list[str], objective_ids: list[str]) -> list[tuple[str, str | None]]:
    targets: list[tuple[str, str | None]] = []
    for control_id in control_ids:
        if catalog.control(control_id) is None:
            raise not_found("Control", control_id)
        targets.append((control_id, None))
    for objective_id in objective_ids:
        if catalog.objective(objective_id) is None:
            raise not_found("Objective", objective_id)
        targets.append((catalog.control_id_for_objective(objective_id), objective_id))
    return targets


def _get_evidence(session, evidence_id: int) -> Evidence:
    row = session.get(Evidence, evidence_id)
    if row is None:
        raise not_found("Evidence", evidence_id)
    return row


def _links(session, evidence_id: int) -> list[EvidenceLink]:
    return list(session.exec(select(EvidenceLink).where(EvidenceLink.evidence_id == evidence_id)).all())


@router.get("/systems/{system_id}/evidence", response_model=list[EvidenceRead])
def list_evidence(
    system_id: int,
    session: SessionDep,
    actor: ActorDep,
    kind: EvidenceKind | None = Query(default=None),
    control_id: str | None = Query(default=None),
    source: EvidenceSource | None = Query(default=None),
    expired: bool | None = Query(default=None),
) -> list[EvidenceRead]:
    """The evidence library, newest first, with its requirement links."""
    get_system_or_404(session, system_id)
    query = select(Evidence).where(Evidence.system_id == system_id)
    if kind is not None:
        query = query.where(Evidence.kind == kind)
    if source is not None:
        query = query.where(Evidence.source == source)
    rows = list(session.exec(query).all())
    by_evidence = links_by_evidence(session, [r.id for r in rows if r.id is not None])
    if control_id:
        rows = [r for r in rows if any(link.control_id == control_id for link in by_evidence.get(r.id, []))]
    if expired is not None:
        rows = [r for r in rows if is_expired(r.expires_at) == expired]
    rows.sort(key=lambda r: (r.collected_at or r.created_at), reverse=True)
    return [to_evidence_read(row, by_evidence.get(row.id, [])) for row in rows]


@router.post(
    "/systems/{system_id}/evidence", response_model=EvidenceRead, status_code=status.HTTP_201_CREATED
)
def create_evidence(
    system_id: int,
    session: SessionDep,
    actor: ActorDep,
    title: Annotated[str, Form(min_length=1, max_length=300)],
    kind: Annotated[EvidenceKind, Form()] = EvidenceKind.document,
    description: Annotated[str | None, Form()] = None,
    collected_at: Annotated[datetime | None, Form()] = None,
    expires_at: Annotated[datetime | None, Form()] = None,
    control_ids: Annotated[list[str] | None, Form()] = None,
    objective_ids: Annotated[list[str] | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
) -> EvidenceRead:
    """Store an artifact (optionally with a file) and link it to the requirements it supports."""
    system = get_system_or_404(session, system_id)
    targets = _link_targets(_parse_ids(control_ids), _parse_ids(objective_ids))

    row = Evidence(
        system_id=system.id,
        title=title,
        kind=kind,
        description=description,
        collected_at=collected_at or utcnow(),
        expires_at=expires_at,
        source=EvidenceSource.manual,
    )
    if file is not None and file.filename:
        payload = file.file.read()
        if not payload:
            raise bad_request("Uploaded file is empty")
        digest = hashlib.sha256(payload).hexdigest()
        name = safe_file_name(file.filename)
        directory = get_settings().evidence_dir / str(system.id)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{digest[:12]}_{name}"
        path.write_bytes(payload)
        row.file_name = name
        row.file_path = str(path)
        row.content_type = file.content_type
        row.size_bytes = len(payload)
        row.sha256 = digest
    session.add(row)
    session.flush()
    for control_id, objective_id in targets:
        session.add(EvidenceLink(evidence_id=row.id, control_id=control_id, objective_id=objective_id))
    log_activity(
        session,
        actor,
        "create",
        "evidence",
        row.id,
        f"Added evidence '{title}' linked to {len(targets)} requirement(s)",
        system_id=system.id,
    )
    session.commit()
    session.refresh(row)
    return to_evidence_read(row, _links(session, row.id))


@router.get("/evidence/{evidence_id}", response_model=EvidenceRead)
def read_evidence(evidence_id: int, session: SessionDep, actor: ActorDep) -> EvidenceRead:
    row = _get_evidence(session, evidence_id)
    return to_evidence_read(row, _links(session, row.id))


@router.put("/evidence/{evidence_id}", response_model=EvidenceRead)
def update_evidence(
    evidence_id: int, payload: EvidenceUpdate, session: SessionDep, actor: ActorDep
) -> EvidenceRead:
    row = _get_evidence(session, evidence_id)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(row, field, value)
    if changes:
        row.updated_at = utcnow()
        session.add(row)
        log_activity(
            session,
            actor,
            "update",
            "evidence",
            row.id,
            f"Updated {', '.join(sorted(changes))} on evidence {row.id}",
            system_id=row.system_id,
        )
        session.commit()
        session.refresh(row)
    return to_evidence_read(row, _links(session, row.id))


@router.delete("/evidence/{evidence_id}", response_model=OkResponse)
def delete_evidence(evidence_id: int, session: SessionDep, actor: ActorDep) -> OkResponse:
    """Delete the record, its links and the stored file."""
    row = _get_evidence(session, evidence_id)
    for link in _links(session, row.id):
        session.delete(link)
    session.flush()
    if row.file_path:
        path = Path(row.file_path)
        evidence_root = get_settings().evidence_dir.resolve()
        try:
            resolved = path.resolve()
            if resolved.is_file() and resolved.is_relative_to(evidence_root):
                resolved.unlink()
        except OSError:
            pass
    system_id, title = row.system_id, row.title
    session.delete(row)
    log_activity(session, actor, "delete", "evidence", evidence_id, f"Deleted evidence '{title}'",
                 system_id=system_id)
    session.commit()
    return OkResponse()


@router.get("/evidence/{evidence_id}/download")
def download_evidence(evidence_id: int, session: SessionDep, actor: ActorDep) -> FileResponse:
    """Return the stored file. The path is re-validated against the evidence directory."""
    row = _get_evidence(session, evidence_id)
    if not row.file_path:
        raise bad_request(f"Evidence {evidence_id} has no file attached")
    path = Path(row.file_path).resolve()
    evidence_root = get_settings().evidence_dir.resolve()
    if not path.is_relative_to(evidence_root) or not path.is_file():
        raise not_found("Evidence file", evidence_id)
    return FileResponse(
        path,
        media_type=row.content_type or "application/octet-stream",
        filename=row.file_name or f"evidence-{evidence_id}",
    )


@router.post("/evidence/{evidence_id}/links", response_model=EvidenceLinkRead,
             status_code=status.HTTP_201_CREATED)
def add_link(
    evidence_id: int, payload: EvidenceLinkCreate, session: SessionDep, actor: ActorDep
) -> EvidenceLinkRead:
    """Link existing evidence to another requirement or assessment objective."""
    row = _get_evidence(session, evidence_id)
    targets = _link_targets(
        [payload.control_id] if payload.objective_id is None else [],
        [payload.objective_id] if payload.objective_id else [],
    )
    control_id, objective_id = targets[0]
    existing = session.exec(
        select(EvidenceLink).where(
            EvidenceLink.evidence_id == row.id,
            EvidenceLink.control_id == control_id,
            EvidenceLink.objective_id == objective_id,
        )
    ).first()
    if existing is not None:
        return EvidenceLinkRead.model_validate(existing)
    link = EvidenceLink(evidence_id=row.id, control_id=control_id, objective_id=objective_id)
    session.add(link)
    log_activity(
        session,
        actor,
        "create",
        "evidence_link",
        row.id,
        f"Linked evidence {row.id} to {objective_id or control_id}",
        system_id=row.system_id,
    )
    session.commit()
    session.refresh(link)
    return EvidenceLinkRead.model_validate(link)


@router.delete("/evidence/{evidence_id}/links/{link_id}", response_model=OkResponse)
def delete_link(evidence_id: int, link_id: int, session: SessionDep, actor: ActorDep) -> OkResponse:
    row = _get_evidence(session, evidence_id)
    link = session.get(EvidenceLink, link_id)
    if link is None or link.evidence_id != row.id:
        raise not_found("Evidence link", link_id)
    target = link.objective_id or link.control_id
    session.delete(link)
    log_activity(session, actor, "delete", "evidence_link", row.id,
                 f"Unlinked evidence {row.id} from {target}", system_id=row.system_id)
    session.commit()
    return OkResponse()
