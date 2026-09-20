"""Per-system control implementation routes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from bulwark import catalog
from bulwark.models import (
    ActivityLog,
    AgentReport,
    Asset,
    CheckResult,
    Evidence,
    EvidenceLink,
    PoamItem,
    PoamMilestone,
)


@pytest.fixture
def sid(system: dict) -> int:
    return system["id"]


def test_list_shape_and_order(client: TestClient, sid: int) -> None:
    response = client.get(f"/api/systems/{sid}/controls")
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 110
    assert [r["control"]["id"] for r in rows] == catalog.control_ids()
    first = rows[0]
    assert set(first) == {
        "control",
        "implementation",
        "objective_counts",
        "evidence_count",
        "check_summary",
        "open_poam_count",
        "warnings",
    }
    assert first["control"]["id"] == "3.1.1"
    assert first["control"]["weight"] == 5
    assert "discussion" not in first["control"]
    assert first["implementation"]["status"] == "not_implemented"
    assert first["implementation"]["responsibility"] == "customer"
    assert first["implementation"]["partial_credit"] == "none"
    assert first["objective_counts"] == {"met": 0, "not_met": 0, "not_applicable": 0, "unknown": 6,
        "total": 6}
    assert first["evidence_count"] == 0
    assert first["check_summary"] is None
    assert first["open_poam_count"] == 0
    assert first["warnings"] == []
    assert sum(r["objective_counts"]["total"] for r in rows) == 320
    assert client.get("/api/systems/9999/controls").status_code == 404


def test_detail(client: TestClient, sid: int) -> None:
    response = client.get(f"/api/systems/{sid}/controls/3.1.1")
    assert response.status_code == 200
    body = response.json()
    assert body["control"]["discussion"]
    assert body["control"]["assessment"]["examine"]
    assert [o["objective_id"] for o in body["objectives"]] == catalog.objective_ids_for("3.1.1")
    assert {o["status"] for o in body["objectives"]} == {"unknown"}
    assert body["objectives"][0]["text"]
    assert body["provider"] is None and body["responsibility_row"] is None
    assert body["evidence"] == [] and body["check_results"] == [] and body["poam_items"] == []
    assert client.get(f"/api/systems/{sid}/controls/9.9.9").status_code == 404
    assert client.get("/api/systems/9999/controls/3.1.1").status_code == 404


def test_put_status_and_narrative(client: TestClient, sid: int, db_session: Session) -> None:
    before = datetime.now(UTC) - timedelta(seconds=2)
    response = client.put(
        f"/api/systems/{sid}/controls/3.1.1",
        json={"status": "implemented", "implementation_narrative": "AD security groups gate CUI shares."},
    )
    assert response.status_code == 200
    impl = response.json()["implementation"]
    assert impl["status"] == "implemented"
    assert impl["implementation_narrative"].startswith("AD security")
    assert impl["assessed_by"] == "admin"
    assert datetime.fromisoformat(impl["assessed_at"].replace("Z", "+00:00")) >= before
    assert response.json()["warnings"] == []

    # partial update keeps other fields
    again = client.put(f"/api/systems/{sid}/controls/3.1.1", json={"notes": "reviewed"})
    assert again.json()["implementation"]["status"] == "implemented"
    assert again.json()["implementation"]["notes"] == "reviewed"

    assert client.get("/api/systems").json()[0]["score_summary"]["met_count"] == 1
    assert client.put(f"/api/systems/{sid}/controls/3.1.1", json={"status": "done"}).status_code == 422
    assert client.put(f"/api/systems/{sid}/controls/9.9.9", json={"status": "planned"}).status_code == 404

    entries = db_session.exec(
        select(ActivityLog).where(ActivityLog.entity_type == "control_implementation")
    ).all()
    assert entries and "3.1.1" in entries[0].summary


def test_put_na_justification_warning(client: TestClient, sid: int) -> None:
    response = client.put(f"/api/systems/{sid}/controls/3.1.18", json={"status": "not_applicable"})
    assert response.status_code == 200
    assert any("justification" in w for w in response.json()["warnings"])
    listed = next(r for r in client.get(f"/api/systems/{sid}/controls").json() if r["control"]["id"] == \
        "3.1.18")
    assert listed["warnings"]
    fixed = client.put(
        f"/api/systems/{sid}/controls/3.1.18", json={"na_justification": "No mobile devices access CUI."}
    )
    assert fixed.json()["warnings"] == []
    assert client.get("/api/systems").json()[0]["score_summary"]["met_count"] == 1


def test_partial_credit_validation(client: TestClient, sid: int) -> None:
    url = f"/api/systems/{sid}/controls"
    wrong_control = client.put(f"{url}/3.1.1", json={"status": "partially_implemented",
        "partial_credit": "mfa_partial"})
    assert wrong_control.status_code == 400
    assert "3.5.3" in wrong_control.json()["detail"]

    wrong_kind = client.put(f"{url}/3.13.11", json={"status": "partially_implemented",
        "partial_credit": "mfa_partial"})
    assert wrong_kind.status_code == 400
    assert "encryption_non_fips" in wrong_kind.json()["detail"]

    wrong_status = client.put(f"{url}/3.5.3", json={"status": "implemented", "partial_credit": "mfa_partial"})
    assert wrong_status.status_code == 400
    assert "partially_implemented" in wrong_status.json()["detail"]

    ok = client.put(f"{url}/3.5.3", json={"status": "partially_implemented", "partial_credit": "mfa_partial"})
    assert ok.status_code == 200
    assert ok.json()["implementation"]["partial_credit"] == "mfa_partial"

    fips = client.put(
        f"{url}/3.13.11", json={"status": "partially_implemented", "partial_credit": "encryption_non_fips"}
    )
    assert fips.status_code == 200

    # leaving partially_implemented resets the flag
    reset = client.put(f"{url}/3.5.3", json={"status": "implemented"})
    assert reset.json()["implementation"]["partial_credit"] == "none"
    # explicit "none" is always accepted
    assert client.put(f"{url}/3.1.1", json={"partial_credit": "none"}).status_code == 200
    assert client.put(f"{url}/3.5.3", json={"partial_credit": "bogus"}).status_code == 422


def test_provider_link_validation(client: TestClient, sid: int) -> None:
    bad = client.put(f"/api/systems/{sid}/controls/3.1.1", json={"provider_id": 999})
    assert bad.status_code == 400
    assert "provider" in bad.json()["detail"].lower()

    provider = client.post("/api/providers", json={"name": "Microsoft 365 GCC High", "kind": "csp"}).json()
    client.put(f"/api/providers/{provider['id']}/matrix", json=[{"control_id": "3.1.1", "model": "shared"}])

    unlinked = client.put(f"/api/systems/{sid}/controls/3.1.1", json={"responsibility": "shared"})
    assert any("no provider" in w for w in unlinked.json()["warnings"])

    linked = client.put(f"/api/systems/{sid}/controls/3.1.1", json={"provider_id": provider["id"]})
    assert linked.status_code == 200
    assert linked.json()["provider"]["name"] == "Microsoft 365 GCC High"
    assert linked.json()["responsibility_row"]["model"] == "shared"
    assert linked.json()["warnings"] == []

    cleared = client.put(f"/api/systems/{sid}/controls/3.1.1", json={"provider_id": None})
    assert cleared.json()["implementation"]["provider_id"] is None


def test_objectives_bulk(client: TestClient, sid: int) -> None:
    url = f"/api/systems/{sid}/controls/3.1.1/objectives"
    bad = client.put(url, json=[{"objective_id": "3.1.2[a]", "status": "met"}])
    assert bad.status_code == 400
    assert "3.1.2[a]" in bad.json()["detail"]
    assert client.put(url, json=[{"objective_id": "3.1.1[a]", "status": "maybe"}]).status_code == 422

    response = client.put(
        url,
        json=[
            {"objective_id": "3.1.1[a]", "status": "met", "notes": "user list reviewed"},
            {"objective_id": "3.1.1[b]", "status": "not_met"},
            {"objective_id": "3.1.1[c]", "status": "not_applicable"},
        ],
    )
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 6
    by_id = {r["objective_id"]: r for r in rows}
    assert by_id["3.1.1[a]"]["status"] == "met" and by_id["3.1.1[a]"]["notes"] == "user list reviewed"
    assert by_id["3.1.1[b]"]["status"] == "not_met"
    assert by_id["3.1.1[c]"]["status"] == "not_applicable"
    assert by_id["3.1.1[d]"]["status"] == "unknown"

    detail = client.get(f"/api/systems/{sid}/controls/3.1.1").json()
    assert detail["objective_counts"] == {"met": 1, "not_met": 1, "not_applicable": 1, "unknown": 3,
        "total": 6}

    client.put(f"/api/systems/{sid}/controls/3.1.1", json={"status": "implemented"})
    listed = client.get(f"/api/systems/{sid}/controls").json()[0]
    assert listed["objective_counts"]["not_met"] == 1
    assert any("partially implemented" in w for w in listed["warnings"])
    assert client.put(f"/api/systems/{sid}/controls/9.9.9/objectives", json=[]).status_code == 404


def test_bulk_update(client: TestClient, sid: int) -> None:
    url = f"/api/systems/{sid}/controls/bulk"
    bad = client.post(url, json=[{"control_id": "3.2.1", "status": "planned"}, {"control_id": "9.9.9"}])
    assert bad.status_code == 400
    assert "9.9.9" in bad.json()["detail"]
    # validation happens before any write
    listed = {r["control"]["id"]: r for r in client.get(f"/api/systems/{sid}/controls").json()}
    assert listed["3.2.1"]["implementation"]["status"] == "not_implemented"

    provider = client.post("/api/providers", json={"name": "MSP Co", "kind": "msp"}).json()
    response = client.post(
        url,
        json=[
            {"control_id": "3.2.1", "status": "planned"},
            {"control_id": "3.2.2", "status": "implemented", "responsibility": "provider",
                "provider_id": provider["id"]},
            {"control_id": "3.2.3"},
        ],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["updated"] == 2
    impls = {i["control_id"]: i for i in body["implementations"]}
    assert impls["3.2.1"]["status"] == "planned"
    assert impls["3.2.2"]["responsibility"] == "provider" and impls["3.2.2"]["provider_id"] == provider["id"]
    assert client.get("/api/systems").json()[0]["score_summary"]["met_count"] == 1
    assert client.post(url, json=[{"control_id": "3.2.1", "provider_id": 999}]).status_code == 400
    assert client.post("/api/systems/9999/controls/bulk", json=[]).status_code == 404


def test_evidence_poam_and_check_counts(client: TestClient, sid: int, db_session: Session) -> None:
    evidence = Evidence(system_id=sid, title="Access control policy", kind="policy")
    other = Evidence(system_id=sid, title="Screenshot", kind="screenshot")
    db_session.add_all([evidence, other])
    db_session.flush()
    db_session.add_all(
        [
            EvidenceLink(evidence_id=evidence.id, control_id="3.1.1"),
            EvidenceLink(evidence_id=evidence.id, control_id="3.1.1", objective_id="3.1.1[a]"),
            EvidenceLink(evidence_id=other.id, control_id="3.1.1"),
            EvidenceLink(evidence_id=evidence.id, control_id="3.1.2"),
        ]
    )
    open_item = PoamItem(system_id=sid, control_id="3.1.1", title="Open", status="open")
    progress = PoamItem(system_id=sid, control_id="3.1.1", title="Progress", status="in_progress")
    closed = PoamItem(system_id=sid, control_id="3.1.1", title="Closed", status="closed")
    db_session.add_all([open_item, progress, closed])
    db_session.flush()
    db_session.add(PoamMilestone(poam_item_id=open_item.id, description="Step 1", position=1))

    in_scope = Asset(system_id=sid, name="CNC-01", category="cui")
    out_scope = Asset(system_id=sid, name="LOBBY-TV", category="out_of_scope")
    db_session.add_all([in_scope, out_scope])
    db_session.flush()
    report = AgentReport(asset_id=in_scope.id, system_id=sid, hostname="CNC-01")
    report2 = AgentReport(asset_id=out_scope.id, system_id=sid, hostname="LOBBY-TV")
    db_session.add_all([report, report2])
    db_session.flush()
    collected = datetime(2026, 9, 20, 14, 3, tzinfo=UTC)
    db_session.add_all(
        [
            CheckResult(
                report_id=report.id, asset_id=in_scope.id, system_id=sid,
                    check_id="os.accounts.guest_disabled",
                status="pass", control_ids_json='["3.1.1"]', objective_ids_json='["3.1.1[a]"]',
                collected_at=collected, details_json='{"guest": "disabled"}',
            ),
            CheckResult(
                report_id=report.id, asset_id=in_scope.id, system_id=sid, check_id="os.inventory.local_users",
                status="fail", control_ids_json='["3.1.1", "3.5.1"]', collected_at=collected,
            ),
            CheckResult(
                report_id=report.id, asset_id=in_scope.id, system_id=sid, check_id="os.inventory.local_users",
                status="pass", control_ids_json='["3.1.1", "3.5.1"]', is_latest=False,
            ),
            CheckResult(
                report_id=report2.id, asset_id=out_scope.id, system_id=sid,
                    check_id="os.accounts.guest_disabled",
                status="fail", control_ids_json='["3.1.1"]',
            ),
        ]
    )
    db_session.commit()

    rows = {r["control"]["id"]: r for r in client.get(f"/api/systems/{sid}/controls").json()}
    assert rows["3.1.1"]["evidence_count"] == 2
    assert rows["3.1.2"]["evidence_count"] == 1
    assert rows["3.1.1"]["open_poam_count"] == 2
    assert rows["3.1.1"]["check_summary"] == {
        "total": 2, "passing": 1, "failing": 1, "errors": 0, "info": 0, "not_applicable": 0, "assets": 1,
        "last_collected_at": "2026-09-20T14:03:00Z",
    }
    assert rows["3.5.1"]["check_summary"]["failing"] == 1
    assert rows["3.1.3"]["check_summary"] is None

    detail = client.get(f"/api/systems/{sid}/controls/3.1.1").json()
    assert [e["title"] for e in detail["evidence"]] == sorted([e["title"] for e in detail["evidence"]],
        reverse=True)
    assert len(detail["evidence"]) == 2
    policy = next(e for e in detail["evidence"] if e["title"] == "Access control policy")
    assert len(policy["links"]) == 3 and policy["expired"] is False
    assert len(detail["check_results"]) == 2
    assert all(r["is_latest"] for r in detail["check_results"])
    guest = next(r for r in detail["check_results"] if r["check_id"] == "os.accounts.guest_disabled")
    assert guest["details"] == {"guest": "disabled"} and guest["control_ids"] == ["3.1.1"]
    assert detail["check_summary"]["failing"] == 1
    assert {p["title"] for p in detail["poam_items"]} == {"Open", "Progress", "Closed"}
    assert next(p for p in detail["poam_items"] if p["title"] == "Open")["milestones"][0]["description"] \
        == "Step 1"
    assert detail["open_poam_count"] == 2
