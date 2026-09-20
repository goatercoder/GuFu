"""Agent enrollment, report ingestion, agent status and findings."""

from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import FileResponse

from ..activity import log_activity
from ..auth import require_enrollment_key
from ..config import PROJECT_DIR, get_settings
from ..evidence_rules import agent_status, findings_for_system, ingest_report
from ..models import System
from ..schemas import (
    AgentReportIn,
    AgentStatusItem,
    EnrollmentInfo,
    EnrollmentInstall,
    FindingItem,
    IngestResponse,
)
from .deps import ActorDep, SessionDep, bad_request, get_system_or_404, not_found

router = APIRouter(tags=["agents"])

AGENT_DIR = PROJECT_DIR / "agent"
DOWNLOADABLE = {
    "bulwark_agent.py": "text/x-python",
    "Bulwark-Agent.ps1": "text/plain",
}
SystemFromKey = Annotated[System, Depends(require_enrollment_key)]


def _server_url(request: Request) -> str:
    configured = get_settings().server_url
    if configured:
        return configured.rstrip("/")
    return str(request.base_url).rstrip("/")


def _install_commands(server: str, key: str) -> EnrollmentInstall:
    """Ready-to-paste install commands. The key is a secret: these are shown in the UI only."""
    return EnrollmentInstall(
        windows=(
            "powershell -ExecutionPolicy Bypass -Command \""
            f"Invoke-WebRequest -Uri '{server}/api/agents/download/Bulwark-Agent.ps1' "
            "-OutFile \\\"$env:ProgramData\\Bulwark-Agent.ps1\\\"; "
            f"& \\\"$env:ProgramData\\Bulwark-Agent.ps1\\\" -Server '{server}' -Key '{key}' "
            "-InstallScheduledTask\""
        ),
        linux=(
            f"curl -fsSL {server}/api/agents/download/bulwark_agent.py -o /usr/local/bin/bulwark_agent.py "
            f"&& sudo python3 /usr/local/bin/bulwark_agent.py --server {server} --key {key} "
            "--install-schedule"
        ),
        macos=(
            f"curl -fsSL {server}/api/agents/download/bulwark_agent.py -o /usr/local/bin/bulwark_agent.py "
            f"&& sudo python3 /usr/local/bin/bulwark_agent.py --server {server} --key {key} "
            "--install-schedule"
        ),
    )


@router.get("/systems/{system_id}/enrollment", response_model=EnrollmentInfo)
def read_enrollment(system_id: int, request: Request, session: SessionDep, actor: ActorDep) -> EnrollmentInfo:
    """The enrollment key and the commands that install an agent against it."""
    system = get_system_or_404(session, system_id)
    server = _server_url(request)
    return EnrollmentInfo(
        system_id=system.id,
        enrollment_key=system.enrollment_key,
        server_url=server,
        install=_install_commands(server, system.enrollment_key),
    )


@router.post("/systems/{system_id}/enrollment/rotate", response_model=EnrollmentInfo)
def rotate_enrollment(
    system_id: int, request: Request, session: SessionDep, actor: ActorDep
) -> EnrollmentInfo:
    """Issue a new enrollment key. Existing agents stop reporting until they are reconfigured."""
    system = get_system_or_404(session, system_id)
    system.enrollment_key = secrets.token_urlsafe(24)
    session.add(system)
    log_activity(
        session,
        actor,
        "rotate",
        "system",
        system.id,
        "Rotated the agent enrollment key; existing agents must be reconfigured",
        system_id=system.id,
    )
    session.commit()
    session.refresh(system)
    server = _server_url(request)
    return EnrollmentInfo(
        system_id=system.id,
        enrollment_key=system.enrollment_key,
        server_url=server,
        install=_install_commands(server, system.enrollment_key),
    )


@router.get("/agents/download/{filename}")
def download_agent(filename: str) -> FileResponse:
    """Serve the collector scripts so an endpoint can install without a file share."""
    media_type = DOWNLOADABLE.get(filename)
    if media_type is None:
        raise not_found("Agent script", filename)
    path = Path(AGENT_DIR) / filename
    if not path.is_file():
        raise not_found("Agent script", filename)
    return FileResponse(path, media_type=media_type, filename=filename)


@router.post("/agents/report", response_model=IngestResponse)
def post_report(payload: AgentReportIn, system: SystemFromKey, session: SessionDep) -> IngestResponse:
    """Ingest a report. Authenticated with the system's enrollment key, never the admin password."""
    result = ingest_report(session, system, payload)
    session.commit()
    return result


@router.post("/systems/{system_id}/agent-reports/upload", response_model=IngestResponse)
def upload_report(
    system_id: int,
    session: SessionDep,
    actor: ActorDep,
    payload: AgentReportIn | None = None,
    file: Annotated[UploadFile | None, File()] = None,
) -> IngestResponse:
    """Offline path: an administrator uploads a report file produced with ``--output``."""
    system = get_system_or_404(session, system_id)
    if file is not None:
        raw = file.file.read()
        try:
            data: Any = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise bad_request(f"Uploaded file is not valid JSON: {exc}") from exc
        payload = AgentReportIn.model_validate(data)
    if payload is None:
        raise bad_request("Provide a report file or a JSON body")
    result = ingest_report(session, system, payload, actor=actor)
    session.commit()
    return result


@router.get("/systems/{system_id}/agent-status", response_model=list[AgentStatusItem])
def read_agent_status(system_id: int, session: SessionDep, actor: ActorDep) -> list[AgentStatusItem]:
    """Which endpoints are reporting, how recently, and how they are doing."""
    get_system_or_404(session, system_id)
    return [AgentStatusItem.model_validate(row) for row in agent_status(session, system_id)]


@router.get("/systems/{system_id}/findings", response_model=list[FindingItem])
def read_findings(system_id: int, session: SessionDep, actor: ActorDep) -> list[FindingItem]:
    """Failing automated checks grouped by the requirement they provide evidence for."""
    get_system_or_404(session, system_id)
    return [FindingItem.model_validate(row) for row in findings_for_system(session, system_id)]
