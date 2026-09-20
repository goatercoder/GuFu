"""``/api/auth/*``: admin login/logout and session introspection (no auth required)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import func
from sqlmodel import select

from ..activity import log_activity
from ..auth import ADMIN_ACTOR, clear_session_cookie, is_admin_request, set_session_cookie, verify_password
from ..models import Organization, System
from ..schemas import AuthMeResponse, LoginRequest, OkResponse
from .deps import SessionDep

router = APIRouter(prefix="/auth", tags=["auth"])


def _setup_complete(session) -> bool:  # noqa: ANN001
    org_count = session.exec(select(func.count()).select_from(Organization)).one()
    if not org_count:
        return False
    system_count = session.exec(select(func.count()).select_from(System)).one()
    return bool(system_count)


@router.post("/login", response_model=OkResponse)
def login(
    body: LoginRequest, request: Request, response: Response, session: SessionDep
) -> OkResponse:
    """Exchange the admin password for a signed ``bulwark_session`` cookie."""
    if not verify_password(body.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid password")
    set_session_cookie(response, request=request)
    log_activity(session, ADMIN_ACTOR, "login", "session", None, "Admin logged in")
    session.commit()
    return OkResponse()


@router.post("/logout", response_model=OkResponse)
def logout(response: Response) -> OkResponse:
    clear_session_cookie(response)
    return OkResponse()


@router.get("/me", response_model=AuthMeResponse)
def me(request: Request, session: SessionDep) -> AuthMeResponse:
    """``{authenticated, setup_complete}``; ``setup_complete`` = organization and >= 1 system exist."""
    return AuthMeResponse(authenticated=is_admin_request(request), setup_complete=_setup_complete(session))
