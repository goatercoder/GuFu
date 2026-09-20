"""Shared fixtures: every test gets a fresh data directory + SQLite file via environment variables."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

ADMIN_PASSWORD = "test-admin-password"
SECRET = "unit-test-secret-not-for-production"


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point Bulwark at a temporary data dir and reset every process-level cache."""
    monkeypatch.setenv("BULWARK_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BULWARK_ADMIN_PASSWORD", ADMIN_PASSWORD)
    monkeypatch.setenv("BULWARK_SECRET", SECRET)
    monkeypatch.setenv("BULWARK_CRM_TEMPLATES_DIR", str(tmp_path / "crm_templates"))
    monkeypatch.setenv("BULWARK_FRONTEND_DIST", str(tmp_path / "no-frontend"))
    monkeypatch.delenv("BULWARK_CATALOG_PATH", raising=False)

    from bulwark.auth import reset_auth_cache
    from bulwark.catalog import clear_cache
    from bulwark.config import get_settings
    from bulwark.db import reset_engine

    get_settings.cache_clear()
    reset_engine()
    reset_auth_cache()
    clear_cache()
    yield tmp_path
    reset_engine()
    get_settings.cache_clear()
    reset_auth_cache()


@pytest.fixture
def app(env: Path) -> FastAPI:
    from bulwark.main import create_app

    return create_app()


@pytest.fixture
def anon_client(app: FastAPI) -> Iterator[TestClient]:
    """Client that has not logged in (runs the lifespan, so the schema exists)."""
    with TestClient(app) as client:
        yield client


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """Client logged in as admin through the session cookie."""
    with TestClient(app) as client:
        response = client.post("/api/auth/login", json={"password": ADMIN_PASSWORD})
        assert response.status_code == 200, response.text
        assert "bulwark_session" in response.cookies
        yield client


@pytest.fixture
def db_session(app: FastAPI) -> Iterator[Session]:
    """Direct database access for asserting side effects and seeding rows."""
    from bulwark.db import get_engine, init_db

    init_db()
    with Session(get_engine()) as session:
        yield session


@pytest.fixture
def org(client: TestClient) -> dict:
    response = client.put(
        "/api/organization",
        json={
            "name": "Precision Machining LLC",
            "cage_code": "1ABC2",
            "industry": "Precision machining",
            "employee_count": 40,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def system(client: TestClient, org: dict) -> dict:
    response = client.post(
        "/api/systems",
        json={"name": "Shop network", "environment": "hybrid", "cui_types": "ITAR drawings"},
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def org_system(org: dict, system: dict) -> tuple[dict, dict]:
    return org, system
