"""Security properties that must hold for a system holding a company's compliance record.

These are the guarantees an assessor (or an attacker) would probe: nothing readable without
authentication, an enrollment key that is not an administrative credential, evidence files that
cannot escape their directory, and secrets that never reach a log or a generated document.
"""

from __future__ import annotations

import io
import json

import pytest
from fastapi.testclient import TestClient

from tests.conftest import ADMIN_PASSWORD

PROTECTED_PATHS = [
    "/api/systems",
    "/api/organization",
    "/api/providers",
    "/api/catalog",
    "/api/admin/activity",
    "/api/systems/1/score",
    "/api/systems/1/readiness",
    "/api/systems/1/controls",
    "/api/systems/1/poam",
    "/api/systems/1/evidence",
    "/api/systems/1/assets",
    "/api/systems/1/enrollment",
    "/api/systems/1/agent-status",
    "/api/systems/1/findings",
    "/api/systems/1/ssp",
    "/api/systems/1/poam/export",
    "/api/systems/1/readiness-report",
]


@pytest.fixture
def seeded(client: TestClient) -> dict:
    return client.post("/api/admin/seed-demo").json()


@pytest.fixture
def key(client: TestClient, seeded: dict) -> str:
    return client.get(f"/api/systems/{seeded['system_id']}/enrollment").json()["enrollment_key"]


# ------------------------------------------------------------------ authentication
@pytest.mark.parametrize("path", PROTECTED_PATHS)
def test_every_data_route_requires_authentication(anon_client, path):
    assert anon_client.get(path).status_code == 401


def test_write_routes_require_authentication(anon_client):
    assert anon_client.post("/api/admin/seed-demo").status_code == 401
    assert anon_client.put("/api/organization", json={"name": "Attacker"}).status_code == 401
    assert anon_client.post("/api/systems", json={"name": "Attacker"}).status_code == 401
    assert anon_client.delete("/api/systems/1").status_code == 401


def test_health_is_public(anon_client):
    assert anon_client.get("/api/health").status_code == 200


def test_a_wrong_password_is_rejected(anon_client):
    assert anon_client.post("/api/auth/login", json={"password": "wrong"}).status_code == 401
    assert anon_client.post("/api/auth/login", json={"password": ""}).status_code == 422


def test_the_session_cookie_is_http_only_and_same_site(anon_client):
    response = anon_client.post("/api/auth/login", json={"password": ADMIN_PASSWORD})
    header = response.headers.get("set-cookie", "")
    assert "httponly" in header.lower()
    assert "samesite=lax" in header.lower()


def test_the_cookie_is_marked_secure_behind_a_tls_proxy(anon_client):
    """Plain localhost must keep working, but a proxied HTTPS request gets a Secure cookie."""
    plain = anon_client.post("/api/auth/login", json={"password": ADMIN_PASSWORD})
    assert "secure" not in plain.headers.get("set-cookie", "").lower()

    proxied = anon_client.post(
        "/api/auth/login",
        json={"password": ADMIN_PASSWORD},
        headers={"X-Forwarded-Proto": "https"},
    )
    assert "secure" in proxied.headers.get("set-cookie", "").lower()


def test_logout_clears_the_session(client):
    assert client.get("/api/systems").status_code == 200
    client.post("/api/auth/logout")
    assert client.get("/api/systems").status_code == 401


# ------------------------------------------------------------------ enrollment keys
def test_an_enrollment_key_is_not_an_administrative_credential(anon_client, key):
    headers = {"Authorization": f"Bearer {key}"}
    for path in ("/api/systems", "/api/admin/activity", "/api/systems/1/score",
                 "/api/systems/1/enrollment", "/api/systems/1/ssp"):
        assert anon_client.get(path, headers=headers).status_code == 401, path
    assert anon_client.post("/api/systems/1/enrollment/rotate", headers=headers).status_code == 401
    assert anon_client.post("/api/admin/seed-demo", headers=headers).status_code == 401


def test_an_invalid_key_cannot_report(anon_client, key):
    report = {"schema_version": 1, "agent": {"platform": "linux"},
              "asset": {"hostname": "EVIL"}, "checks": []}
    for token in ("", "guess", key[:-1], key + "x", key.upper()):
        response = anon_client.post(
            "/api/agents/report", json=report, headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 401, token


def test_a_key_only_reports_into_its_own_system(client, anon_client, key, seeded):
    other = client.post("/api/systems", json={"name": "Other system"}).json()["id"]
    report = {"schema_version": 1, "agent": {"platform": "linux"},
              "asset": {"hostname": "CROSSOVER"},
              "checks": [{"check_id": "os.firewall.enabled", "status": "fail", "observed": "off"}]}
    response = anon_client.post(
        "/api/agents/report", json=report, headers={"Authorization": f"Bearer {key}"}
    )
    assert response.json()["system_id"] == seeded["system_id"]
    assert all(a["name"] != "CROSSOVER" for a in client.get(f"/api/systems/{other}/assets").json())


# ------------------------------------------------------------------ evidence files
def test_a_traversing_file_name_cannot_escape_the_evidence_directory(client, system, env):
    response = client.post(
        f"/api/systems/{system['id']}/evidence",
        data={"title": "Traversal", "kind": "document"},
        files={"file": ("../../../../etc/passwd", io.BytesIO(b"payload"), "text/plain")},
    )
    assert response.status_code == 201
    assert "/" not in response.json()["file_name"]
    assert ".." not in response.json()["file_name"]
    root = env / "data" / "evidence"
    for path in root.rglob("*"):
        assert root.resolve() in path.resolve().parents or path.resolve() == root.resolve()


def test_an_empty_upload_is_rejected(client, system):
    response = client.post(
        f"/api/systems/{system['id']}/evidence",
        data={"title": "Empty", "kind": "document"},
        files={"file": ("empty.txt", io.BytesIO(b""), "text/plain")},
    )
    assert response.status_code == 400


def test_downloads_require_authentication(client, anon_client, system):
    created = client.post(
        f"/api/systems/{system['id']}/evidence",
        data={"title": "Policy", "kind": "policy"},
        files={"file": ("p.md", io.BytesIO(b"# policy"), "text/markdown")},
    ).json()
    assert anon_client.get(f"/api/evidence/{created['id']}/download").status_code == 401


# ------------------------------------------------------------------ secrets
def test_secrets_never_reach_the_activity_log_or_documents(client, key, seeded):
    system_id = seeded["system_id"]
    haystacks = {
        "activity log": json.dumps(client.get("/api/admin/activity").json()),
        "system list": json.dumps(client.get("/api/systems").json()),
        "system security plan": client.get(f"/api/systems/{system_id}/ssp",
                                           params={"format": "md"}).text,
        "readiness report": client.get(f"/api/systems/{system_id}/readiness-report",
                                       params={"format": "md"}).text,
        "POA&M export": client.get(f"/api/systems/{system_id}/poam/export",
                                   params={"format": "csv"}).text,
    }
    for name, text in haystacks.items():
        assert ADMIN_PASSWORD not in text, f"admin password appears in the {name}"
        assert key not in text, f"enrollment key appears in the {name}"


def test_rotating_a_key_invalidates_the_previous_one(client, anon_client, key, seeded):
    system_id = seeded["system_id"]
    fresh = client.post(f"/api/systems/{system_id}/enrollment/rotate").json()["enrollment_key"]
    assert fresh != key
    report = {"schema_version": 1, "agent": {"platform": "linux"},
              "asset": {"hostname": "PC"}, "checks": []}
    assert anon_client.post("/api/agents/report", json=report,
                            headers={"Authorization": f"Bearer {key}"}).status_code == 401
    assert anon_client.post("/api/agents/report", json=report,
                            headers={"Authorization": f"Bearer {fresh}"}).status_code == 200


# ------------------------------------------------------------------ input validation
def test_unknown_identifiers_are_not_found(client, system):
    assert client.get(f"/api/systems/{system['id']}/controls/9.9.9").status_code == 404
    assert client.get("/api/systems/99999/score").status_code == 404
    assert client.get("/api/poam/99999").status_code == 404
    assert client.get("/api/evidence/99999").status_code == 404
    assert client.get("/api/providers/99999").status_code == 404


def test_invalid_values_are_rejected(client, system):
    assert client.put(f"/api/systems/{system['id']}/controls/3.1.1",
                      json={"status": "perfect"}).status_code == 422
    assert client.post(f"/api/systems/{system['id']}/poam",
                       json={"control_id": "3.1.1", "title": ""}).status_code == 422
    assert client.get("/api/admin/activity", params={"limit": -5}).status_code == 422
    assert client.get("/api/admin/activity", params={"limit": 100_000}).status_code == 422


def test_an_oversized_report_field_does_not_crash_ingestion(anon_client, key):
    report = {
        "schema_version": 1,
        "agent": {"platform": "linux", "version": "x" * 5000},
        "asset": {"hostname": "BIG", "os_name": "y" * 5000},
        "checks": [{"check_id": "os.firewall.enabled", "status": "pass", "observed": "z" * 50_000}],
    }
    response = anon_client.post("/api/agents/report", json=report,
                                headers={"Authorization": f"Bearer {key}"})
    assert response.status_code == 200
    assert response.json()["checks_ingested"] == 1


# ------------------------------------------------------------------ scoring invariants
def test_scoring_invariants_hold_on_real_data(client, seeded):
    score = client.get(f"/api/systems/{seeded['system_id']}/score").json()
    assert -203 <= score["sprs_score"] <= 110
    assert score["met_count"] + score["not_met_count"] == score["total"] == 110
    assert 110 - sum(d["deducted"] for d in score["deductions"]) == score["sprs_score"]
    assert sum(f["total"] for f in score["families"]) == 110
    assert sum(f["met"] for f in score["families"]) == score["met_count"]
    assert sum(score["by_status"].values()) == 110
