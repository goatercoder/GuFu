"""Admin authentication and enrollment-key authentication."""

from __future__ import annotations

import time

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from bulwark.auth import create_session_token, require_enrollment_key, verify_session_token
from bulwark.models import System

from .conftest import ADMIN_PASSWORD


def test_health_is_public(anon_client: TestClient) -> None:
    response = anon_client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["version"]


def test_protected_routes_reject_anonymous(anon_client: TestClient) -> None:
    for path in ("/api/systems", "/api/catalog", "/api/organization", "/api/providers"):
        response = anon_client.get(path)
        assert response.status_code == 401, path
        assert response.json()["detail"]
    assert anon_client.post("/api/systems", json={"name": "x"}).status_code == 401


def test_bearer_admin_password(anon_client: TestClient) -> None:
    ok = anon_client.get("/api/systems", headers={"Authorization": f"Bearer {ADMIN_PASSWORD}"})
    assert ok.status_code == 200
    bad = anon_client.get("/api/systems", headers={"Authorization": "Bearer wrong"})
    assert bad.status_code == 401
    wrong_scheme = anon_client.get("/api/systems", headers={"Authorization": f"Basic {ADMIN_PASSWORD}"})
    assert wrong_scheme.status_code == 401


def test_login_logout_me(anon_client: TestClient) -> None:
    assert anon_client.get("/api/auth/me").json() == {"authenticated": False, "setup_complete": False}

    bad = anon_client.post("/api/auth/login", json={"password": "nope"})
    assert bad.status_code == 401
    assert bad.json()["detail"] == "Invalid password"
    assert "bulwark_session" not in bad.cookies

    good = anon_client.post("/api/auth/login", json={"password": ADMIN_PASSWORD})
    assert good.status_code == 200
    assert good.json() == {"ok": True}
    assert "bulwark_session" in good.cookies
    assert "httponly" in good.headers["set-cookie"].lower()

    assert anon_client.get("/api/auth/me").json()["authenticated"] is True
    assert anon_client.get("/api/systems").status_code == 200

    assert anon_client.post("/api/auth/logout").status_code == 200
    assert anon_client.get("/api/auth/me").json()["authenticated"] is False
    assert anon_client.get("/api/systems").status_code == 401


def test_setup_complete_flag(client: TestClient) -> None:
    assert client.get("/api/auth/me").json()["setup_complete"] is False
    client.put("/api/organization", json={"name": "Org"})
    assert client.get("/api/auth/me").json()["setup_complete"] is False
    client.post("/api/systems", json={"name": "Sys"})
    assert client.get("/api/auth/me").json() == {"authenticated": True, "setup_complete": True}


def test_tampered_or_expired_cookie_rejected(anon_client: TestClient) -> None:
    anon_client.cookies.set("bulwark_session", "garbage.value")
    assert anon_client.get("/api/systems").status_code == 401
    anon_client.cookies.set("bulwark_session", create_session_token("other-secret", 3600))
    assert anon_client.get("/api/systems").status_code == 401


def test_session_token_roundtrip() -> None:
    token = create_session_token("secret", 60)
    assert verify_session_token("secret", token)
    assert not verify_session_token("secret", token, now=time.time() + 61)
    assert not verify_session_token("other", token)
    assert not verify_session_token("secret", token[:-2] + "zz")
    assert not verify_session_token("secret", None)
    assert not verify_session_token("secret", "no-dot")


def test_enrollment_key_is_not_an_admin_credential(client: TestClient, system: dict,
    db_session: Session) -> None:
    row = db_session.exec(select(System).where(System.id == system["id"])).one()
    assert len(row.enrollment_key) == 32
    assert "enrollment_key" not in system
    client.cookies.clear()
    response = client.get("/api/systems", headers={"Authorization": f"Bearer {row.enrollment_key}"})
    assert response.status_code == 401


def test_require_enrollment_key_resolves_system(app: FastAPI, client: TestClient, system: dict,
    db_session: Session) -> None:
    def whoami(enrolled: System = Depends(require_enrollment_key)) -> dict:  # noqa: B008
        return {"system_id": enrolled.id, "name": enrolled.name}

    app.add_api_route("/api/_test/whoami", whoami, methods=["GET"])
    key = db_session.exec(select(System).where(System.id == system["id"])).one().enrollment_key

    assert client.get("/api/_test/whoami").status_code == 401
    assert client.get("/api/_test/whoami", headers={"Authorization": "Bearer nope"}).status_code == 401
    admin = client.get("/api/_test/whoami", headers={"Authorization": f"Bearer {ADMIN_PASSWORD}"})
    assert admin.status_code == 401
    ok = client.get("/api/_test/whoami", headers={"Authorization": f"Bearer {key}"})
    assert ok.status_code == 200
    assert ok.json() == {"system_id": system["id"], "name": "Shop network"}


def test_generated_credentials_written_to_data_dir(env, monkeypatch, capsys) -> None:  # noqa: ANN001
    from bulwark.auth import get_admin_password, get_secret, reset_auth_cache
    from bulwark.config import get_settings

    monkeypatch.delenv("BULWARK_ADMIN_PASSWORD")
    monkeypatch.delenv("BULWARK_SECRET")
    get_settings.cache_clear()
    reset_auth_cache()
    settings = get_settings()

    password = get_admin_password(settings)
    secret = get_secret(settings)
    assert (settings.data_dir / "admin_password.txt").read_text().strip() == password
    assert (settings.data_dir / "secret.key").read_text().strip() == secret
    assert len(password) >= 16 and len(secret) >= 32
    assert "admin_password.txt" in capsys.readouterr().out
    # second call reuses the stored values
    reset_auth_cache()
    assert get_admin_password(settings) == password
    assert get_secret(settings) == secret
