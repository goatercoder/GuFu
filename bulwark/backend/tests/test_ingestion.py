"""Agent report ingestion: assets, evidence, findings and automatic POA&M items (§6)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient


def report(hostname: str = "SHOP-PC-01", checks: list[dict] | None = None, **asset) -> dict:
    payload = {
        "schema_version": 1,
        "agent": {"name": "bulwark-agent", "version": "0.1.0", "platform": "windows"},
        "asset": {
            "hostname": hostname,
            "os_family": "windows",
            "os_name": "Windows 11 Pro",
            "os_version": "10.0.22631",
            "ip_addresses": ["10.0.1.15"],
            "mac_addresses": ["00:11:22:33:44:55"],
            **asset,
        },
        "collected_at": datetime.now(UTC).isoformat(),
        "checks": checks
        if checks is not None
        else [
            {"check_id": "os.firewall.enabled", "status": "pass", "observed": "All profiles On"},
            {"check_id": "os.disk.encryption", "status": "fail", "observed": "C: not encrypted"},
        ],
    }
    return payload


@pytest.fixture
def key(client: TestClient, system: dict) -> str:
    response = client.get(f"/api/systems/{system['id']}/enrollment")
    assert response.status_code == 200, response.text
    return response.json()["enrollment_key"]


def post(client: TestClient, key: str, payload: dict):
    return client.post("/api/agents/report", json=payload, headers={"Authorization": f"Bearer {key}"})


def test_report_creates_the_asset_flagged_for_review(client, system, key):
    response = post(client, key, report())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["checks_ingested"] == 2
    assert body["findings"] == 1

    assets = client.get(f"/api/systems/{system['id']}/assets").json()
    assert len(assets) == 1
    assert assets[0]["name"] == "SHOP-PC-01"
    assert assets[0]["needs_review"] is True
    assert assets[0]["category"] == "cui"
    assert assets[0]["os_name"] == "Windows 11 Pro"
    assert assets[0]["ip_address"] == "10.0.1.15"
    assert assets[0]["agent_version"] == "0.1.0"
    assert assets[0]["agent_last_seen"] is not None


def test_hostname_match_is_case_insensitive_and_does_not_duplicate(client, system, key):
    post(client, key, report("SHOP-PC-01"))
    post(client, key, report("shop-pc-01"))
    assets = client.get(f"/api/systems/{system['id']}/assets").json()
    assert len(assets) == 1


def test_second_report_supersedes_the_previous_result(client, system, key):
    post(client, key, report(checks=[{"check_id": "os.disk.encryption", "status": "fail",
                                      "observed": "not encrypted"}]))
    post(client, key, report(checks=[{"check_id": "os.disk.encryption", "status": "pass",
                                      "observed": "BitLocker on"}]))
    asset_id = client.get(f"/api/systems/{system['id']}/assets").json()[0]["id"]
    results = client.get(f"/api/assets/{asset_id}/checks").json()
    assert len(results) == 1
    assert results[0]["status"] == "pass"
    assert results[0]["is_latest"] is True

    reports = client.get(f"/api/assets/{asset_id}/reports").json()
    assert len(reports) == 2


def test_evidence_is_upserted_not_duplicated_and_expires(client, system, key):
    post(client, key, report())
    post(client, key, report())
    evidence = client.get(f"/api/systems/{system['id']}/evidence", params={"source": "agent"}).json()
    assert len(evidence) == 2  # one per check, not per report
    item = next(e for e in evidence if e["check_id"] == "os.firewall.enabled")
    assert item["kind"] == "agent_check"
    assert item["check_status"] == "pass"
    assert item["expires_at"] is not None
    expires = datetime.fromisoformat(item["expires_at"])
    collected = datetime.fromisoformat(item["collected_at"])
    assert timedelta(days=29) < (expires - collected) < timedelta(days=31)
    assert any(link["control_id"] == "3.13.1" for link in item["links"])
    assert any(link["objective_id"] for link in item["links"])


def test_failing_check_opens_one_poam_item_with_a_milestone(client, system, key):
    post(client, key, report())
    items = client.get(f"/api/systems/{system['id']}/poam").json()
    disk = [i for i in items if i["check_id"] == "os.disk.encryption"]
    assert len(disk) >= 1
    item = disk[0]
    assert item["source"] == "agent"
    assert item["status"] == "open"
    assert item["scheduled_completion"] is not None
    assert len(item["milestones"]) == 1
    assert item["risk_level"] in ("low", "moderate", "high")


def test_repeated_failures_do_not_open_duplicate_items(client, system, key):
    post(client, key, report())
    first = len(client.get(f"/api/systems/{system['id']}/poam").json())
    post(client, key, report())
    post(client, key, report())
    assert len(client.get(f"/api/systems/{system['id']}/poam").json()) == first


def test_recovery_is_noted_but_the_item_stays_open(client, system, key):
    post(client, key, report())
    post(client, key, report(checks=[{"check_id": "os.disk.encryption", "status": "pass",
                                      "observed": "BitLocker on"}]))
    items = client.get(f"/api/systems/{system['id']}/poam").json()
    item = next(i for i in items if i["check_id"] == "os.disk.encryption")
    assert item["status"] == "open"
    assert "now passing" in (item["notes"] or "")


def test_risk_level_follows_the_point_value(client, system, key):
    post(
        client,
        key,
        report(checks=[
            {"check_id": "os.firewall.enabled", "status": "fail", "observed": "off"},        # 3.13.1 = 5
            {"check_id": "os.session.logon_banner", "status": "fail", "observed": "none"},   # 3.1.9 = 1
        ]),
    )
    items = {i["control_id"]: i for i in client.get(f"/api/systems/{system['id']}/poam").json()}
    assert items["3.13.1"]["risk_level"] == "high"
    assert items["3.1.9"]["risk_level"] == "low"


def test_unknown_check_is_stored_without_a_mapping(client, system, key):
    response = post(client, key, report(checks=[{"check_id": "vendor.custom.thing", "status": "pass",
                                                 "observed": "ok"}]))
    assert response.json()["unknown_checks"] == ["vendor.custom.thing"]
    asset_id = client.get(f"/api/systems/{system['id']}/assets").json()[0]["id"]
    result = client.get(f"/api/assets/{asset_id}/checks").json()[0]
    assert result["control_ids"] == []


def test_findings_group_by_control_and_list_assets(client, system, key):
    post(client, key, report("PC-1", checks=[{"check_id": "os.firewall.enabled", "status": "fail",
                                              "observed": "off"}]))
    post(client, key, report("PC-2", checks=[{"check_id": "os.firewall.enabled", "status": "fail",
                                              "observed": "off"}]))
    findings = client.get(f"/api/systems/{system['id']}/findings").json()
    boundary = next(f for f in findings if f["control_id"] == "3.13.1")
    assert boundary["asset_count"] == 2
    assert {a["asset_name"] for a in boundary["assets"]} == {"PC-1", "PC-2"}
    assert boundary["weight"] == 5
    assert boundary["poam_item_id"] is not None


def test_out_of_scope_assets_do_not_produce_findings(client, system, key):
    post(client, key, report("MKT-LAPTOP"))
    asset = client.get(f"/api/systems/{system['id']}/assets").json()[0]
    client.put(f"/api/assets/{asset['id']}", json={"category": "out_of_scope",
                                                   "category_rationale": "Guest VLAN, no CUI"})
    post(client, key, report("MKT-LAPTOP"))
    assert client.get(f"/api/systems/{system['id']}/findings").json() == []


def test_agent_status_reports_counts_and_staleness(client, system, key):
    post(client, key, report())
    status = client.get(f"/api/systems/{system['id']}/agent-status").json()
    assert len(status) == 1
    assert status[0]["pass_count"] == 1
    assert status[0]["fail_count"] == 1
    assert status[0]["stale"] is False
    assert status[0]["platform"] == "windows"


def test_a_wrong_key_is_rejected(client, key):
    assert post(client, "not-the-key", report()).status_code == 401


def test_the_admin_session_cannot_post_agent_reports(client):
    """The report endpoint accepts the enrollment key only."""
    assert client.post("/api/agents/report", json=report()).status_code == 401


def test_the_enrollment_key_cannot_reach_admin_routes(client, anon_client, system, key):
    """An enrollment key authenticates agents only; it is not an administrative credential."""
    response = anon_client.get(
        f"/api/systems/{system['id']}/poam", headers={"Authorization": f"Bearer {key}"}
    )
    assert response.status_code == 401
    assert anon_client.get(f"/api/systems/{system['id']}/enrollment",
                           headers={"Authorization": f"Bearer {key}"}).status_code == 401


def test_rotating_the_key_invalidates_the_old_one(client, system, key):
    new_key = client.post(f"/api/systems/{system['id']}/enrollment/rotate").json()["enrollment_key"]
    assert new_key != key
    assert post(client, key, report()).status_code == 401
    assert post(client, new_key, report()).status_code == 200


def test_offline_upload_accepts_the_same_payload(client, system):
    import io
    import json

    payload = json.dumps(report("OFFLINE-PC")).encode()
    response = client.post(
        f"/api/systems/{system['id']}/agent-reports/upload",
        files={"file": ("report.json", io.BytesIO(payload), "application/json")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["checks_ingested"] == 2
    assert client.get(f"/api/systems/{system['id']}/assets").json()[0]["name"] == "OFFLINE-PC"


def test_offline_upload_rejects_broken_json(client, system):
    import io

    response = client.post(
        f"/api/systems/{system['id']}/agent-reports/upload",
        files={"file": ("report.json", io.BytesIO(b"{not json"), "application/json")},
    )
    assert response.status_code == 400
    assert "JSON" in response.json()["detail"]


def test_enrollment_install_commands_reference_the_key(client, system, key):
    install = client.get(f"/api/systems/{system['id']}/enrollment").json()["install"]
    assert key in install["windows"] and key in install["linux"] and key in install["macos"]
    assert "Bulwark-Agent.ps1" in install["windows"]
    assert "bulwark_agent.py" in install["linux"]
