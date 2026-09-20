"""Evidence library: upload, link, download, expire, delete."""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def upload(client: TestClient, system_id: int, **kwargs):
    data = {"title": kwargs.pop("title", "Access Control Policy"), "kind": kwargs.pop("kind", "policy")}
    data.update({k: v for k, v in kwargs.items() if k != "file"})
    files = kwargs.get("file")
    return client.post(f"/api/systems/{system_id}/evidence", data=data, files=files)


@pytest.fixture
def evidence(client: TestClient, system: dict) -> dict:
    response = upload(
        client,
        system["id"],
        control_ids=["3.1.1", "3.1.2"],
        file={"file": ("policy.md", io.BytesIO(b"# Access Control Policy\n"), "text/markdown")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_upload_stores_the_file_and_links(client, evidence):
    assert evidence["file_name"] == "policy.md"
    assert evidence["size_bytes"] == 24
    assert evidence["source"] == "manual"
    assert {link["control_id"] for link in evidence["links"]} == {"3.1.1", "3.1.2"}
    assert evidence["expired"] is False


def test_upload_without_a_file_is_allowed(client, system):
    response = upload(client, system["id"], title="Verbal attestation", kind="attestation")
    assert response.status_code == 201
    assert response.json()["file_name"] is None


def test_objective_links_resolve_their_control(client, system):
    response = upload(client, system["id"], objective_ids=["3.1.1[a]"])
    link = response.json()["links"][0]
    assert link["control_id"] == "3.1.1"
    assert link["objective_id"] == "3.1.1[a]"


def test_control_ids_accept_a_json_array_or_comma_list(client, system):
    response = upload(client, system["id"], control_ids='["3.1.1","3.1.2"]')
    assert len(response.json()["links"]) == 2
    response = upload(client, system["id"], control_ids="3.3.1,3.3.2")
    assert {link["control_id"] for link in response.json()["links"]} == {"3.3.1", "3.3.2"}


def test_unknown_control_is_rejected(client, system):
    assert upload(client, system["id"], control_ids=["9.9.9"]).status_code == 404


def test_download_returns_the_bytes(client, evidence):
    response = client.get(f"/api/evidence/{evidence['id']}/download")
    assert response.status_code == 200
    assert response.content == b"# Access Control Policy\n"


def test_download_without_a_file_is_a_bad_request(client, system):
    item = upload(client, system["id"], title="No file").json()
    assert client.get(f"/api/evidence/{item['id']}/download").status_code == 400


def test_a_traversing_file_name_is_neutralised(client, system, env):
    response = upload(
        client,
        system["id"],
        file={"file": ("../../etc/passwd", io.BytesIO(b"root:x:0:0"), "text/plain")},
    )
    body = response.json()
    assert body["file_name"] == "passwd"  # directory components are stripped, not encoded
    stored = Path(env / "data" / "evidence" / str(system["id"]))
    assert all(".." not in child.name for child in stored.iterdir())
    assert client.get(f"/api/evidence/{body['id']}/download").content == b"root:x:0:0"


def test_filters(client, system, evidence):
    upload(client, system["id"], title="Screenshot", kind="screenshot", control_ids=["3.3.1"])
    base = f"/api/systems/{system['id']}/evidence"
    assert len(client.get(base).json()) == 2
    assert len(client.get(base, params={"kind": "screenshot"}).json()) == 1
    assert len(client.get(base, params={"control_id": "3.1.1"}).json()) == 1
    assert len(client.get(base, params={"source": "manual"}).json()) == 2


def test_expiry_filter(client, system):
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    upload(client, system["id"], title="Old scan", kind="config_export", expires_at=past)
    upload(client, system["id"], title="Current policy")
    base = f"/api/systems/{system['id']}/evidence"
    expired = client.get(base, params={"expired": True}).json()
    assert [e["title"] for e in expired] == ["Old scan"]
    assert expired[0]["expired"] is True
    assert len(client.get(base, params={"expired": False}).json()) == 1


def test_link_and_unlink(client, evidence):
    link = client.post(f"/api/evidence/{evidence['id']}/links",
                       json={"control_id": "3.4.1"}).json()
    assert link["control_id"] == "3.4.1"
    again = client.post(f"/api/evidence/{evidence['id']}/links", json={"control_id": "3.4.1"}).json()
    assert again["id"] == link["id"]  # idempotent
    assert client.delete(f"/api/evidence/{evidence['id']}/links/{link['id']}").status_code == 200
    assert len(client.get(f"/api/evidence/{evidence['id']}").json()["links"]) == 2


def test_update_metadata(client, evidence):
    response = client.put(f"/api/evidence/{evidence['id']}",
                          json={"title": "Access Control Policy v2", "description": "Reviewed"})
    assert response.json()["title"] == "Access Control Policy v2"


def test_delete_removes_the_file(client, evidence, env):
    stored = Path(env / "data" / "evidence" / "1")
    assert any(stored.iterdir())
    assert client.delete(f"/api/evidence/{evidence['id']}").status_code == 200
    assert client.get(f"/api/evidence/{evidence['id']}").status_code == 404
    assert not any(stored.iterdir())


def test_evidence_requires_authentication(anon_client, system):
    assert anon_client.get(f"/api/systems/{system['id']}/evidence").status_code == 401
