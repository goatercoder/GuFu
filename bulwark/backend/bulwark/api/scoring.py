"""Score, score history and the readiness view."""

from __future__ import annotations

import json
from datetime import date, timedelta

from fastapi import APIRouter, status
from sqlmodel import select

from .. import catalog, scoring
from ..activity import log_activity
from ..evidence_rules import agent_status, findings_for_system, latest_results
from ..models import (
    Asset,
    AssetCategory,
    CheckStatus,
    ControlImplementation,
    Evidence,
    EvidenceLink,
    ObjectiveAssessment,
    PoamItem,
    PoamStatus,
    Provider,
    Responsibility,
    ResponsibilityRow,
    ScoreSnapshot,
    utcnow,
)
from ..schemas import (
    Contradiction,
    NextAction,
    ReadinessResponse,
    ScoreResult,
    ScoreSnapshotRead,
)
from .deps import ActorDep, SessionDep, get_system_or_404, is_expired

router = APIRouter(prefix="/systems/{system_id}", tags=["scoring"])

#: A POA&M item older than this is called out: 32 CFR 170.21 gives 180 days to close one.
POAM_AGE_LIMIT_DAYS = 180


def control_states(session, system_id: int) -> list[scoring.ControlState]:
    """Build the pure-scoring input from the database."""
    impls = list(
        session.exec(select(ControlImplementation).where(ControlImplementation.system_id == system_id)).all()
    )
    by_impl: dict[int, dict[str, str]] = {}
    if impls:
        rows = session.exec(
            select(ObjectiveAssessment).where(
                ObjectiveAssessment.implementation_id.in_([i.id for i in impls])  # type: ignore[union-attr]
            )
        ).all()
        for row in rows:
            by_impl.setdefault(row.implementation_id, {})[row.objective_id] = str(row.status)
    return [
        scoring.ControlState(
            control_id=impl.control_id,
            status=str(impl.status),
            partial_credit=str(impl.partial_credit),
            na_justification=impl.na_justification,
            objective_statuses=by_impl.get(impl.id, {}),
        )
        for impl in impls
    ]


def compute_score(session, system_id: int) -> dict:
    return scoring.score(control_states(session, system_id), catalog.controls())


@router.get("/score", response_model=ScoreResult)
def read_score(system_id: int, session: SessionDep, actor: ActorDep) -> ScoreResult:
    """Live SPRS score for the system."""
    get_system_or_404(session, system_id)
    return ScoreResult.model_validate(compute_score(session, system_id))


@router.get("/score/history", response_model=list[ScoreSnapshotRead])
def read_history(system_id: int, session: SessionDep, actor: ActorDep) -> list[ScoreSnapshotRead]:
    """Saved snapshots, oldest first, for the trend chart."""
    get_system_or_404(session, system_id)
    rows = session.exec(
        select(ScoreSnapshot).where(ScoreSnapshot.system_id == system_id).order_by(ScoreSnapshot.taken_at)
    ).all()
    return [ScoreSnapshotRead.model_validate(row) for row in rows]


@router.post("/score/snapshot", response_model=ScoreSnapshotRead, status_code=status.HTTP_201_CREATED)
def take_snapshot(system_id: int, session: SessionDep, actor: ActorDep) -> ScoreSnapshotRead:
    """Freeze today's score so progress is provable later."""
    system = get_system_or_404(session, system_id)
    result = compute_score(session, system_id)
    snapshot = ScoreSnapshot(
        system_id=system.id,
        taken_at=utcnow(),
        sprs_score=result["sprs_score"],
        met_count=result["met_count"],
        total_count=result["total"],
        readiness_pct=result["readiness_pct"],
        conditional_eligible=result["conditional_eligible"],
        details_json=json.dumps(
            {
                "families": result["families"],
                "by_status": result["by_status"],
                "conditional_blockers": result["conditional_blockers"],
            }
        ),
    )
    session.add(snapshot)
    log_activity(
        session,
        actor,
        "create",
        "score_snapshot",
        None,
        f"Snapshot taken: SPRS {result['sprs_score']}, {result['met_count']}/{result['total']} met",
        system_id=system.id,
    )
    session.commit()
    session.refresh(snapshot)
    return ScoreSnapshotRead.model_validate(snapshot)


def _pct(covered: int, total: int) -> dict[str, float | int]:
    """Coverage as a plain dict so every consumer (API, reports) sees the same shape."""
    return {"covered": covered, "total": total, "pct": round(covered / total * 100, 1) if total else 0.0}


def readiness(session, system_id: int) -> dict:
    """Everything the dashboard needs beyond the score itself."""
    result = compute_score(session, system_id)
    states = control_states(session, system_id)

    # Evidence coverage: objectives with at least one non-expired evidence link.
    evidence_rows = list(session.exec(select(Evidence).where(Evidence.system_id == system_id)).all())
    live_ids = {e.id for e in evidence_rows if not is_expired(e.expires_at)}
    stale_count = len(evidence_rows) - len(live_ids)
    covered_objectives: set[str] = set()
    if evidence_rows:
        links = session.exec(
            select(EvidenceLink).where(
                EvidenceLink.evidence_id.in_([e.id for e in evidence_rows])  # type: ignore[union-attr]
            )
        ).all()
        for link in links:
            if link.evidence_id in live_ids and link.objective_id:
                covered_objectives.add(link.objective_id)
    total_objectives = sum(len(c["objectives"]) for c in catalog.controls())

    # Automated coverage: requirements with a passing check on at least one in-scope asset.
    in_scope = {
        a.id
        for a in session.exec(select(Asset).where(Asset.system_id == system_id)).all()
        if a.category != AssetCategory.out_of_scope
    }
    passing_controls: set[str] = set()
    for row in latest_results(session, system_id, statuses={CheckStatus.passed.value}):
        if row.asset_id in in_scope:
            passing_controls.update(json.loads(row.control_ids_json or "[]"))
    checkable = {c["id"] for c in catalog.controls() if c.get("check_ids")}

    # Contradictions: a requirement recorded as met while a live endpoint check disproves it.
    failing_by_control: dict[str, list[str]] = {}
    for row in latest_results(session, system_id, statuses={CheckStatus.fail.value}):
        if row.asset_id not in in_scope:
            continue
        for control_id in json.loads(row.control_ids_json or "[]"):
            failing_by_control.setdefault(control_id, []).append(row.check_id)
    contradictions = []
    for state in states:
        if state.status not in ("implemented", "not_applicable"):
            continue
        checks_failing = sorted(set(failing_by_control.get(state.control_id, [])))
        if not checks_failing:
            continue
        control = catalog.control(state.control_id) or {}
        contradictions.append(
            {
                "control_id": state.control_id,
                "cmmc_id": control.get("cmmc_id"),
                "name": control.get("name", ""),
                "weight": control.get("weight", 0),
                "recorded_status": state.status,
                "failing_checks": checks_failing,
            }
        )
    contradictions.sort(key=lambda c: (-c["weight"], c["control_id"]))

    # POA&M health.
    items = list(session.exec(select(PoamItem).where(PoamItem.system_id == system_id)).all())
    today = date.today()
    open_items = [i for i in items if i.status in (PoamStatus.open, PoamStatus.in_progress)]
    overdue = [
        i for i in open_items if i.scheduled_completion is not None and i.scheduled_completion < today
    ]
    aging = [
        i
        for i in open_items
        if i.identified_at is not None and (today - i.identified_at) > timedelta(days=POAM_AGE_LIMIT_DAYS)
    ]

    # Assets and agents.
    assets = list(session.exec(select(Asset).where(Asset.system_id == system_id)).all())
    agents = agent_status(session, system_id)

    # Inheritance gaps: a requirement handed to a provider with nothing backing it up.
    providers = {p.id: p for p in session.exec(select(Provider)).all()}
    matrix_rows = {
        (row.provider_id, row.control_id)
        for row in session.exec(select(ResponsibilityRow)).all()
        if row.model in ("provider", "shared")
    }
    gaps: list[str] = []
    for impl in session.exec(
        select(ControlImplementation).where(ControlImplementation.system_id == system_id)
    ).all():
        if impl.responsibility in (Responsibility.provider, Responsibility.inherited, Responsibility.shared):
            control = catalog.control(impl.control_id) or {}
            label = control.get("cmmc_id", impl.control_id)
            if impl.provider_id is None:
                gaps.append(f"{label}: responsibility is {impl.responsibility.value} but no provider is set")
            elif impl.provider_id not in providers:
                gaps.append(f"{label}: assigned to a provider that no longer exists")
            elif (impl.provider_id, impl.control_id) not in matrix_rows:
                name = providers[impl.provider_id].name
                gaps.append(
                    f"{label}: {name} has no responsibility-matrix row covering this requirement"
                )

    return {
        "system_id": system_id,
        "score": result,
        "evidence_coverage": _pct(len(covered_objectives), total_objectives),
        "automated_coverage": _pct(len(passing_controls & checkable), len(checkable)),
        "stale_evidence_count": stale_count,
        "overdue_poam_count": len(overdue),
        "aging_poam_count": len(aging),
        "open_poam_count": len(open_items),
        "findings_count": len(findings_for_system(session, system_id)),
        "assets_needing_review": sum(1 for a in assets if a.needs_review),
        "assets_total": len(assets),
        "agents_reporting": sum(1 for a in agents if not a["stale"]),
        "agents_stale": sum(1 for a in agents if a["stale"]),
        "inheritance_gaps": sorted(gaps)[:20],
        "contradictions": contradictions[:25],
        "contradiction_count": len(contradictions),
        "next_actions": scoring.next_actions(states, catalog.controls(), limit=10),
        "generated_at": utcnow(),
    }


@router.get("/readiness", response_model=ReadinessResponse)
def read_readiness(system_id: int, session: SessionDep, actor: ActorDep) -> ReadinessResponse:
    """Assessment readiness: score, coverage, POA&M health and what to do next."""
    get_system_or_404(session, system_id)
    data = readiness(session, system_id)
    data["score"] = ScoreResult.model_validate(data["score"])
    data["next_actions"] = [NextAction.model_validate(a) for a in data["next_actions"]]
    data["contradictions"] = [Contradiction.model_validate(c) for c in data["contradictions"]]
    return ReadinessResponse.model_validate(data)
