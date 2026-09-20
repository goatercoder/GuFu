"""Authentication.

* Admin: a single password (``BULWARK_ADMIN_PASSWORD`` or auto-generated into
  ``data/admin_password.txt``). ``POST /api/auth/login`` exchanges it for a signed, expiring
  ``bulwark_session`` cookie. Admin routes also accept ``Authorization: Bearer <admin password>``.
* Agents: ``Authorization: Bearer <enrollment key>`` resolves the :class:`~bulwark.models.System`.

Session tokens are ``base64url(payload).base64url(hmac_sha256(secret, payload))`` where the
payload is JSON ``{"exp": <unix ts>, "iat": <unix ts>, "n": <nonce>}``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response, status
from sqlmodel import Session, select

from .config import Settings, get_settings
from .db import get_session
from .models import System

log = logging.getLogger(__name__)

SESSION_COOKIE = "bulwark_session"
ADMIN_ACTOR = "admin"

_admin_password_cache: dict[str, str] = {}
_secret_cache: dict[str, str] = {}


def reset_auth_cache() -> None:
    """Forget cached credentials (tests switch data directories between runs)."""
    _admin_password_cache.clear()
    _secret_cache.clear()


def _write_private_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(content)


def get_admin_password(settings: Settings | None = None) -> str:
    """Admin password from settings, else from/into ``data/admin_password.txt``."""
    settings = settings or get_settings()
    if settings.admin_password:
        return settings.admin_password
    key = str(settings.data_dir)
    cached = _admin_password_cache.get(key)
    if cached:
        return cached
    path = settings.data_dir / "admin_password.txt"
    if path.is_file():
        password = path.read_text(encoding="utf-8").strip()
    else:
        password = ""
    if not password:
        password = secrets.token_urlsafe(18)
        _write_private_file(path, password + "\n")
        print(
            "\n"
            "=====================================================================\n"
            " Bulwark generated an admin password on first run.\n"
            f" It is stored in: {path}\n"
            f" Admin password: {password}\n"
            " Set BULWARK_ADMIN_PASSWORD to choose your own.\n"
            "=====================================================================\n",
            flush=True,
        )
    _admin_password_cache[key] = password
    return password


def get_secret(settings: Settings | None = None) -> str:
    """Cookie-signing secret from settings, else from/into ``data/secret.key``."""
    settings = settings or get_settings()
    if settings.secret:
        return settings.secret
    key = str(settings.data_dir)
    cached = _secret_cache.get(key)
    if cached:
        return cached
    path = settings.data_dir / "secret.key"
    secret = path.read_text(encoding="utf-8").strip() if path.is_file() else ""
    if not secret:
        secret = secrets.token_urlsafe(48)
        _write_private_file(path, secret + "\n")
        log.info("Generated a new session secret at %s", path)
    _secret_cache[key] = secret
    return secret


def ensure_credentials(settings: Settings | None = None) -> None:
    """Materialise the admin password and secret at startup so notices print early."""
    settings = settings or get_settings()
    get_admin_password(settings)
    get_secret(settings)


# --------------------------------------------------------------------------------------------
# Session tokens
# --------------------------------------------------------------------------------------------
def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _sign(secret: str, payload: bytes) -> str:
    return _b64encode(hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).digest())


def create_session_token(secret: str, ttl_seconds: int) -> str:
    now = int(time.time())
    payload = json.dumps({"iat": now, "exp": now + ttl_seconds, "n": secrets.token_hex(8)}).encode("utf-8")
    encoded = _b64encode(payload)
    return f"{encoded}.{_sign(secret, payload)}"


def verify_session_token(secret: str, token: str | None, now: float | None = None) -> bool:
    """True when ``token`` carries a valid signature and has not expired."""
    if not token or "." not in token:
        return False
    encoded, signature = token.rsplit(".", 1)
    try:
        payload = _b64decode(encoded)
    except (ValueError, TypeError):
        return False
    if not hmac.compare_digest(_sign(secret, payload), signature):
        return False
    try:
        data = json.loads(payload)
        exp = int(data["exp"])
    except (ValueError, TypeError, KeyError):
        return False
    return (now if now is not None else time.time()) < exp


def set_session_cookie(response: Response, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    ttl = settings.session_ttl_hours * 3600
    token = create_session_token(get_secret(settings), ttl)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=ttl,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )
    return token


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


# --------------------------------------------------------------------------------------------
# Request inspection
# --------------------------------------------------------------------------------------------
def bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization") or ""
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()


def verify_password(candidate: str, settings: Settings | None = None) -> bool:
    expected = get_admin_password(settings)
    return hmac.compare_digest(candidate.encode("utf-8"), expected.encode("utf-8"))


def is_admin_request(request: Request) -> bool:
    settings = get_settings()
    cookie = request.cookies.get(SESSION_COOKIE)
    if cookie and verify_session_token(get_secret(settings), cookie):
        return True
    token = bearer_token(request)
    return bool(token and verify_password(token, settings))


def require_admin(request: Request) -> str:
    """Dependency: valid session cookie or ``Bearer <admin password>``; returns the actor name."""
    if is_admin_request(request):
        return ADMIN_ACTOR
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated: log in or send Authorization: Bearer <admin password>",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_enrollment_key(request: Request, session: Annotated[Session, Depends(get_session)]) -> System:
    """Dependency for agent routes: resolves the System from ``Bearer <enrollment key>``."""
    token = bearer_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing enrollment key: send Authorization: Bearer <enrollment key>",
            headers={"WWW-Authenticate": "Bearer"},
        )
    system = session.exec(select(System).where(System.enrollment_key == token)).first()
    if system is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid enrollment key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return system


AdminDep = Annotated[str, Depends(require_admin)]
EnrolledSystemDep = Annotated[System, Depends(require_enrollment_key)]
