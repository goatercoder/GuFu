"""The demo seed and the readiness view it produces."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bulwark import scoring


@pytest.fixture
def seeded(client: TestClient) -> dict:
    response = client.post("/api/admin/seed-demo")
    assert response.status_code == 200, response.text
    return response.json()


def test_seed_creates_a_complete_demo(client, seeded):
    sid = seeded["system_id"]
    assert seeded["agent_reports"] == 2
    assert len(client.get(f"/api/systems/{sid}/assets").json()) == 12
    assert len(client.get("/api/providers").json()) == 2
    assert len(client.get(f"/api/systems/{sid}/controls").json()) == 110
    assert client.get("/api/organization").json()["cage_code"] == "1AB23"


def test_seed_is_idempotent(client, seeded):
    again = client.post("/api/admin/seed-demo").json()
    assert again["created_system"] == 0
    assert again["system_id"] == seeded["system_id"]
    assert len(client.get("/api/systems").json()) == 1
    assert len(client.get(f"/api/systems/{seeded['system_id']}/assets").json()) == 12
    assert len(client.get("/api/providers").json()) == 2


def test_seeded_score_is_realistic_and_in_range(client, seeded):
    score = client.get(f"/api/systems/{seeded['system_id']}/score").json()
    assert scoring.MIN_SCORE <= score["sprs_score"] <= scoring.MAX_SCORE
    assert score["sprs_score"] == 80
    assert score["met_count"] == 100
    assert score["na_count"] == 3
    assert score["conditional_eligible"] is False
    assert any("below the minimum" in b for b in score["conditional_blockers"])


def test_partial_credit_is_applied_to_both_requirements(client, seeded):
    deductions = {
        d["control_id"]: d for d in client.get(f"/api/systems/{seeded['system_id']}/score").json()
        ["deductions"]
    }
    assert deductions["3.5.3"]["deducted"] == 3
    assert deductions["3.13.11"]["deducted"] == 3


def test_readiness_surfaces_agent_findings(client, seeded):
    readiness = client.get(f"/api/systems/{seeded['system_id']}/readiness").json()
    assert readiness["findings_count"] > 0
    assert readiness["agents_reporting"] == 2
    assert readiness["automated_coverage"]["pct"] > 50
    assert readiness["evidence_coverage"]["total"] == 320
    assert readiness["open_poam_count"] > 0


def test_readiness_finds_requirements_the_endpoints_contradict(client, seeded):
    """The neglected CNC controller disproves requirements the shop claims are implemented."""
    readiness = client.get(f"/api/systems/{seeded['system_id']}/readiness").json()
    assert readiness["contradiction_count"] >= 10
    first = readiness["contradictions"][0]
    assert first["recorded_status"] in ("implemented", "not_applicable")
    assert first["failing_checks"]
    assert first["weight"] >= readiness["contradictions"][-1]["weight"]


def test_next_actions_lead_with_the_heaviest_gaps(client, seeded):
    actions = client.get(f"/api/systems/{seeded['system_id']}/readiness").json()["next_actions"]
    assert actions
    assert actions[0]["points_recoverable"] == 5
    assert all(a["status"] != "implemented" for a in actions)


def test_snapshots_record_progress(client, seeded):
    sid = seeded["system_id"]
    assert client.get(f"/api/systems/{sid}/score/history").json() == []
    snapshot = client.post(f"/api/systems/{sid}/score/snapshot").json()
    assert snapshot["sprs_score"] == 80
    client.put(f"/api/systems/{sid}/controls/3.11.2", json={"status": "implemented"})
    second = client.post(f"/api/systems/{sid}/score/snapshot").json()
    assert second["sprs_score"] == 85
    history = client.get(f"/api/systems/{sid}/score/history").json()
    assert [h["sprs_score"] for h in history] == [80, 85]


def test_system_list_carries_the_score_summary(client, seeded):
    row = client.get("/api/systems").json()[0]
    assert row["score_summary"]["met_count"] == 100
    assert row["score_summary"]["total"] == 110
    assert row["asset_count"] == 12


def test_activity_log_records_the_seed_without_leaking_secrets(client, seeded):
    from tests.conftest import ADMIN_PASSWORD

    entries = client.get("/api/admin/activity").json()
    assert any(e["action"] == "seed" for e in entries)
    key = client.get(f"/api/systems/{seeded['system_id']}/enrollment").json()["enrollment_key"]
    blob = " ".join(e["summary"] for e in entries)
    assert ADMIN_PASSWORD not in blob
    assert key not in blob


def test_inheritance_gap_is_reported(client, seeded):
    """A requirement handed to a provider with no matrix row must be flagged."""
    sid = seeded["system_id"]
    provider_id = client.get("/api/providers").json()[0]["id"]
    client.put(f"/api/systems/{sid}/controls/3.2.1",
               json={"responsibility": "inherited", "provider_id": provider_id})
    client.put(f"/api/providers/{provider_id}/matrix",
               json=[{"control_id": "3.2.1", "model": "not_covered"}])
    gaps = client.get(f"/api/systems/{sid}/readiness").json()["inheritance_gaps"]
    assert any("3.2.1" in gap for gap in gaps)


def test_seeded_ssp_generates(client, seeded):
    response = client.get(f"/api/systems/{seeded['system_id']}/ssp", params={"format": "md"})
    assert response.status_code == 200
    assert "Precision Machining LLC" in response.text
    assert "Shop CUI Enclave" in response.text
    assert len(response.text) > 100_000
