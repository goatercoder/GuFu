"""POA&M register, milestones and the remediation workflow."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def item(client: TestClient, system: dict) -> dict:
    response = client.post(
        f"/api/systems/{system['id']}/poam",
        json={
            "control_id": "3.5.3",
            "title": "Roll out multifactor authentication",
            "weakness_description": "General users sign in with a password only.",
            "owner": "Tom Byrne",
            "scheduled_completion": (date.today() + timedelta(days=30)).isoformat(),
            "milestones": [{"description": "Buy security keys"}, {"description": "Enrol everyone"}],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_create_defaults_risk_from_the_point_value(client, system):
    response = client.post(
        f"/api/systems/{system['id']}/poam", json={"control_id": "3.5.3", "title": "MFA"}
    )
    assert response.json()["risk_level"] == "high"  # 5-point requirement
    response = client.post(
        f"/api/systems/{system['id']}/poam", json={"control_id": "3.1.4", "title": "Duties"}
    )
    assert response.json()["risk_level"] == "low"  # 1-point requirement


def test_create_records_milestones_in_order(client, item):
    assert [m["description"] for m in item["milestones"]] == ["Buy security keys", "Enrol everyone"]
    assert [m["position"] for m in item["milestones"]] == [0, 1]
    assert item["identified_at"] == date.today().isoformat()


def test_create_rejects_an_unknown_requirement(client, system):
    response = client.post(
        f"/api/systems/{system['id']}/poam", json={"control_id": "9.9.9", "title": "Nope"}
    )
    assert response.status_code == 404


def test_update_and_delete(client, item):
    response = client.put(f"/api/poam/{item['id']}", json={"owner": "Janet Rowe", "cost_estimate": "$4,000"})
    assert response.json()["owner"] == "Janet Rowe"
    assert response.json()["cost_estimate"] == "$4,000"
    assert client.delete(f"/api/poam/{item['id']}").status_code == 200
    assert client.get(f"/api/poam/{item['id']}").status_code == 404


@pytest.mark.parametrize(
    ("first", "second"),
    [("in_progress", "completed"), ("completed", "closed"), ("risk_accepted", "closed")],
)
def test_valid_transitions(client, item, first, second):
    assert client.post(f"/api/poam/{item['id']}/transition",
                       json={"status": first}).status_code == 200
    response = client.post(f"/api/poam/{item['id']}/transition",
                           json={"status": second, "note": "signed off"})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == second


def test_completion_stamps_the_date_and_notes_the_move(client, item):
    client.post(f"/api/poam/{item['id']}/transition", json={"status": "in_progress"})
    body = client.post(f"/api/poam/{item['id']}/transition",
                       json={"status": "completed", "note": "keys deployed"}).json()
    assert body["actual_completion"] == date.today().isoformat()
    assert "keys deployed" in body["notes"]
    assert "open -> in_progress" in body["notes"]


def test_closing_straight_from_open_is_rejected(client, item):
    response = client.post(f"/api/poam/{item['id']}/transition", json={"status": "closed"})
    assert response.status_code == 400
    assert "Cannot move an open item to closed" in response.json()["detail"]


def test_transition_to_the_same_status_is_rejected(client, item):
    response = client.post(f"/api/poam/{item['id']}/transition", json={"status": "open"})
    assert response.status_code == 400


def test_reopening_clears_the_completion_date(client, item):
    client.post(f"/api/poam/{item['id']}/transition", json={"status": "completed"})
    body = client.post(f"/api/poam/{item['id']}/transition", json={"status": "in_progress"}).json()
    assert body["actual_completion"] is None


def test_milestone_lifecycle(client, item):
    created = client.post(f"/api/poam/{item['id']}/milestones",
                          json={"description": "Write the policy"}).json()
    assert created["position"] == 2
    completed = client.put(f"/api/milestones/{created['id']}", json={"completed": True}).json()
    assert completed["completed_at"] is not None
    reopened = client.put(f"/api/milestones/{created['id']}", json={"completed": False}).json()
    assert reopened["completed_at"] is None
    assert client.delete(f"/api/milestones/{created['id']}").status_code == 200
    assert client.delete(f"/api/milestones/{created['id']}").status_code == 404


def test_filters(client, system, item):
    client.post(f"/api/systems/{system['id']}/poam",
                json={"control_id": "3.1.1", "title": "Access review",
                      "scheduled_completion": (date.today() - timedelta(days=5)).isoformat()})
    assert len(client.get(f"/api/systems/{system['id']}/poam",
                          params={"control_id": "3.5.3"}).json()) == 1
    assert len(client.get(f"/api/systems/{system['id']}/poam",
                          params={"overdue": True}).json()) == 1
    client.post(f"/api/poam/{item['id']}/transition", json={"status": "in_progress"})
    assert len(client.get(f"/api/systems/{system['id']}/poam",
                          params={"status": "in_progress"}).json()) == 1


def test_deleting_a_system_removes_its_poam_items(client, system, item):
    client.delete(f"/api/systems/{system['id']}")
    assert client.get(f"/api/poam/{item['id']}").status_code == 404
