"""Systems: seeding on create, list summaries, update and cascade delete."""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import func
from sqlmodel import Session, select

from bulwark.models import (
    ActivityLog,
    AgentReport,
    Asset,
    CheckResult,
    ControlImplementation,
    Evidence,
    EvidenceLink,
    ObjectiveAssessment,
    PoamItem,
    PoamMilestone,
    ScoreSnapshot,
    System,
)


def _count(session: Session, model, *conditions) -> int:  # noqa: ANN001
    stmt = select(func.count()).select_from(model)
    for condition in conditions:
        stmt = stmt.where(condition)
    return session.exec(stmt).one()


def test_create_requires_organization(client: TestClient) -> None:
    response = client.post("/api/systems", json={"name": "Shop"})
    assert response.status_code == 400
    assert "organization" in response.json()["detail"].lower()


def test_create_seeds_implementations_and_objectives(client: TestClient, system: dict,
    db_session: Session) -> None:
    sid = system["id"]
    assert system["name"] == "Shop network"
    assert system["environment"] == "hybrid"
    assert system["status"] == "draft"
    assert system["score_summary"] == {"met_count": 0, "total": 110}
    assert system["asset_count"] == 0
    assert "enrollment_key" not in system
    assert system["created_at"].endswith("Z")

    assert _count(db_session, ControlImplementation, ControlImplementation.system_id == sid) == 110
    impl_ids = select(ControlImplementation.id).where(ControlImplementation.system_id == sid)
    assert _count(db_session, ObjectiveAssessment, ObjectiveAssessment.implementation_id.in_(impl_ids)) == 320
    impl = db_session.exec(
        select(ControlImplementation).where(
            ControlImplementation.system_id == sid, ControlImplementation.control_id == "3.1.1"
        )
    ).one()
    assert impl.status == "not_implemented"
    assert impl.responsibility == "customer"
    statuses = db_session.exec(
        select(ObjectiveAssessment.status).where(ObjectiveAssessment.implementation_id == impl.id)
    ).all()
    assert len(statuses) == 6 and set(statuses) == {"unknown"}

    row = db_session.get(System, sid)
    assert len(row.enrollment_key) == 32

    assert len(client.get(f"/api/systems/{sid}/controls").json()) == 110


def test_list_and_score_summary(client: TestClient, org: dict) -> None:
    a = client.post("/api/systems", json={"name": "A"}).json()
    b = client.post("/api/systems", json={"name": "B"}).json()
    client.put(f"/api/systems/{a['id']}/controls/3.1.1", json={"status": "implemented"})
    client.put(
        f"/api/systems/{a['id']}/controls/3.1.2",
        json={"status": "not_applicable", "na_justification": "No shared accounts"},
    )
    client.put(f"/api/systems/{a['id']}/controls/3.1.3", json={"status": "partially_implemented"})
    client.post(f"/api/systems/{a['id']}/assets", json={"name": "PC-1"})

    listing = client.get("/api/systems").json()
    assert [s["name"] for s in listing] == ["A", "B"]
    by_id = {s["id"]: s for s in listing}
    assert by_id[a["id"]]["score_summary"] == {"met_count": 2, "total": 110}
    assert by_id[a["id"]]["asset_count"] == 1
    assert by_id[b["id"]]["score_summary"] == {"met_count": 0, "total": 110}

    detail = client.get(f"/api/systems/{a['id']}").json()
    assert detail["score_summary"]["met_count"] == 2
    assert client.get("/api/systems/9999").status_code == 404


def test_update_system(client: TestClient, system: dict, db_session: Session) -> None:
    response = client.put(
        f"/api/systems/{system['id']}",
        json={"name": "Renamed", "status": "active", "boundary_description": "Shop floor VLAN"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Renamed"
    assert body["status"] == "active"
    assert body["boundary_description"] == "Shop floor VLAN"
    assert body["environment"] == "hybrid", "untouched fields are preserved"
    assert body["updated_at"] >= body["created_at"]
    assert client.put("/api/systems/9999", json={"name": "x"}).status_code == 404
    assert client.put(f"/api/systems/{system['id']}", json={"environment": "space"}).status_code == 422

    actions = db_session.exec(select(ActivityLog.action).where(ActivityLog.system_id == system["id"])).all()
    assert "create" in actions and "update" in actions


def test_delete_cascades_everything(client: TestClient, system: dict, db_session: Session) -> None:
    sid = system["id"]
    asset = client.post(f"/api/systems/{sid}/assets", json={"name": "SHOP-CNC-01"}).json()
    client.put(f"/api/systems/{sid}/controls/3.1.1", json={"status": "implemented"})

    evidence = Evidence(system_id=sid, title="AC policy", kind="policy")
    db_session.add(evidence)
    db_session.flush()
    db_session.add(EvidenceLink(evidence_id=evidence.id, control_id="3.1.1"))
    poam = PoamItem(system_id=sid, control_id="3.1.2", title="Fix shared accounts")
    db_session.add(poam)
    db_session.flush()
    db_session.add(PoamMilestone(poam_item_id=poam.id, description="Audit accounts", due_date=date(2026,
        12, 1)))
    report = AgentReport(asset_id=asset["id"], system_id=sid, hostname="SHOP-CNC-01")
    db_session.add(report)
    db_session.flush()
    db_session.add(
        CheckResult(
            report_id=report.id,
            asset_id=asset["id"],
            system_id=sid,
            check_id="os.firewall.enabled",
            status="pass",
            control_ids_json='["3.13.1"]',
        )
    )
    db_session.add(
        ScoreSnapshot(system_id=sid, sprs_score=-100, met_count=1, total_count=110, readiness_pct=0.9)
    )
    db_session.commit()

    response = client.delete(f"/api/systems/{sid}")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert client.get(f"/api/systems/{sid}").status_code == 404
    assert client.delete(f"/api/systems/{sid}").status_code == 404
    assert client.get("/api/systems").json() == []

    db_session.expire_all()
    for model in (
        ControlImplementation,
        Asset,
        Evidence,
        PoamItem,
        AgentReport,
        CheckResult,
        ScoreSnapshot,
    ):
        assert _count(db_session, model, model.system_id == sid) == 0, model.__name__
    assert _count(db_session, ObjectiveAssessment) == 0
    assert _count(db_session, EvidenceLink) == 0
    assert _count(db_session, PoamMilestone) == 0
    # history is kept, detached from the deleted system
    assert _count(db_session, ActivityLog, ActivityLog.system_id == sid) == 0
    deleted = db_session.exec(
        select(ActivityLog).where(ActivityLog.action == "delete", ActivityLog.entity_type == "system")
    ).one()
    assert deleted.entity_id == sid and "Shop network" in deleted.summary
