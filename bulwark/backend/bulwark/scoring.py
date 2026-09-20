"""SPRS scoring, conditional-certification eligibility and next actions.

Pure functions: no database, no I/O. The rules come from the *NIST SP 800-171 DoD Assessment
Methodology v1.2.1* as carried into 32 CFR 170.24 (scoring) and 170.21 (POA&M eligibility), and
are stated in ARCHITECTURE.md §5 and docs/scoring.md.

A perfect implementation scores 110. Every requirement that is not met deducts its point value
(5, 3 or 1), so the minimum possible score is -203.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

MAX_SCORE = 110
MIN_SCORE = -203

#: Requirement whose absence stops an assessment: without a system security plan there is
#: nothing to assess. It carries no point value of its own.
SSP_REQUIREMENT = "3.12.4"

#: 32 CFR 170.21(a)(2): these may never sit on a POA&M for a conditional certification.
NEVER_POAM = ("3.1.20", "3.1.22", "3.10.3", "3.10.4", "3.10.5")

#: Minimum SPRS score for a Conditional CMMC Status (80 % of 110).
CONDITIONAL_MIN_SCORE = 88

MET_STATUSES = ("implemented", "not_applicable")
PARTIAL_DEDUCTION = 3


@dataclass(frozen=True)
class ControlState:
    """How one requirement stands, independent of the database."""

    control_id: str
    status: str = "not_implemented"
    partial_credit: str = "none"
    na_justification: str | None = None
    objective_statuses: dict[str, str] = field(default_factory=dict)


def _as_state(item: Any) -> ControlState:
    if isinstance(item, ControlState):
        return item
    return ControlState(
        control_id=item["control_id"],
        status=str(item.get("status", "not_implemented")),
        partial_credit=str(item.get("partial_credit", "none")),
        na_justification=item.get("na_justification"),
        objective_statuses=dict(item.get("objective_statuses") or {}),
    )


def effective_status(state: ControlState) -> tuple[str, list[str]]:
    """The status used for scoring, plus warnings an assessor should see.

    A requirement claimed as implemented while one of its 800-171A objectives is recorded as
    not met is scored as partially implemented: the objectives are what an assessor tests.
    """
    warnings: list[str] = []
    status = state.status
    not_met = [oid for oid, value in state.objective_statuses.items() if value == "not_met"]
    if status == "implemented" and not_met:
        warnings.append(
            f"Claimed implemented but {len(not_met)} assessment objective(s) are not met: "
            + ", ".join(sorted(not_met)[:6])
        )
        status = "partially_implemented"
    if state.status == "not_applicable" and not (state.na_justification or "").strip():
        warnings.append("Marked not applicable without a written justification")
    return status, warnings


def deduction_for(state: ControlState, weight: int) -> tuple[int, str | None]:
    """Points deducted for one requirement, with the reason when partial credit applies."""
    status, _ = effective_status(state)
    if status in MET_STATUSES:
        return 0, None
    if state.control_id == SSP_REQUIREMENT:
        return 0, "No system security plan: the assessment cannot be completed (no point value)"
    if state.control_id == "3.5.3" and state.partial_credit == "mfa_partial":
        return PARTIAL_DEDUCTION, (
            "Partial credit: multifactor authentication is implemented for remote and privileged "
            "users but not for general users"
        )
    if state.control_id == "3.13.11" and state.partial_credit == "encryption_non_fips":
        return PARTIAL_DEDUCTION, (
            "Partial credit: encryption protects CUI but is not FIPS-validated"
        )
    return weight, None


def score(states: list[Any], catalog_controls: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute the SPRS score and everything the dashboard shows (ARCHITECTURE.md §4.4)."""
    by_id = {c["id"]: c for c in catalog_controls}
    state_by_id = {s.control_id: s for s in (_as_state(item) for item in states)}

    deductions: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    by_status: dict[str, int] = {}
    families: dict[str, dict[str, Any]] = {}
    met_count = na_count = 0
    total_deducted = 0
    assessment_blocked = False

    for control_id, control in sorted(by_id.items(), key=lambda kv: _sort_key(kv[0])):
        state = state_by_id.get(control_id, ControlState(control_id=control_id))
        status, control_warnings = effective_status(state)
        weight = int(control.get("weight", 1))
        by_status[state.status] = by_status.get(state.status, 0) + 1

        fam = families.setdefault(
            control["family_id"],
            {
                "id": control["family_id"],
                "abbr": control.get("family_abbr", ""),
                "name": control.get("family_name", ""),
                "met": 0,
                "total": 0,
                "deducted_points": 0,
            },
        )
        fam["total"] += 1

        if control_warnings:
            warnings.append({"control_id": control_id, "messages": control_warnings})

        if status in MET_STATUSES:
            met_count += 1
            fam["met"] += 1
            if status == "not_applicable":
                na_count += 1
            continue

        deducted, reason = deduction_for(state, weight)
        if control_id == SSP_REQUIREMENT:
            assessment_blocked = True
        total_deducted += deducted
        fam["deducted_points"] += deducted
        deductions.append(
            {
                "control_id": control_id,
                "cmmc_id": control.get("cmmc_id"),
                "name": control.get("name", ""),
                "weight": weight,
                "deducted": deducted,
                "status": state.status,
                "reason": reason,
            }
        )

    total = len(by_id)
    not_met_count = total - met_count
    sprs = MAX_SCORE - total_deducted
    conditional, blockers = _conditional_eligibility(
        deductions, sprs, assessment_blocked, by_id, state_by_id
    )

    return {
        "sprs_score": sprs,
        "max_score": MAX_SCORE,
        "min_score": MIN_SCORE,
        "met_count": met_count,
        "not_met_count": not_met_count,
        "na_count": na_count,
        "total": total,
        "readiness_pct": round(met_count / total * 100, 1) if total else 0.0,
        "assessment_blocked": assessment_blocked,
        "conditional_eligible": conditional,
        "conditional_blockers": blockers,
        "final_ready": not_met_count == 0 and not assessment_blocked,
        "deductions": deductions,
        "warnings": warnings,
        "families": [families[k] for k in sorted(families, key=_sort_key)],
        "by_status": by_status,
    }


def _conditional_eligibility(
    deductions: list[dict[str, Any]],
    sprs: int,
    assessment_blocked: bool,
    by_id: dict[str, dict[str, Any]],
    state_by_id: dict[str, ControlState],
) -> tuple[bool, list[str]]:
    """32 CFR 170.21(a)(2): when may the remaining gaps sit on a POA&M?

    A Conditional CMMC Status needs at least 88 points, every outstanding requirement worth
    1 point (3.13.11 may remain at its 3-point partial credit), and none of the five
    requirements that are never POA&M-eligible outstanding.
    """
    blockers: list[str] = []
    if assessment_blocked:
        blockers.append(
            f"{SSP_REQUIREMENT} (system security plan) is not implemented, so the assessment "
            "cannot be completed"
        )
    if sprs < CONDITIONAL_MIN_SCORE:
        blockers.append(f"Score {sprs} is below the minimum of {CONDITIONAL_MIN_SCORE} (80 % of 110)")

    heavy = []
    for item in deductions:
        if item["control_id"] == SSP_REQUIREMENT:
            continue
        if item["control_id"] == "3.13.11" and item["deducted"] == PARTIAL_DEDUCTION:
            continue  # explicitly allowed to remain on a POA&M at partial credit
        if item["deducted"] > 1:
            heavy.append(f"{item['cmmc_id'] or item['control_id']} ({item['deducted']} points)")
    if heavy:
        blockers.append(
            "Requirements worth more than 1 point are not met: " + ", ".join(sorted(heavy)[:10])
        )

    never = [
        by_id[cid].get("cmmc_id", cid)
        for cid in NEVER_POAM
        if cid in by_id
        and effective_status(state_by_id.get(cid, ControlState(control_id=cid)))[0] not in MET_STATUSES
    ]
    if never:
        blockers.append("Requirements that may never sit on a POA&M are not met: " + ", ".join(never))

    return (not blockers), blockers


def next_actions(
    states: list[Any], catalog_controls: list[dict[str, Any]], limit: int = 10
) -> list[dict[str, Any]]:
    """The gaps worth closing first: heaviest deduction, then closest to done."""
    by_id = {c["id"]: c for c in catalog_controls}
    actions: list[dict[str, Any]] = []
    for item in states:
        state = _as_state(item)
        control = by_id.get(state.control_id)
        if control is None:
            continue
        status, _ = effective_status(state)
        if status in MET_STATUSES:
            continue
        weight = int(control.get("weight", 1))
        deducted, reason = deduction_for(state, weight)
        outstanding = sum(
            1 for value in state.objective_statuses.values() if value in ("not_met", "unknown")
        )
        actions.append(
            {
                "control_id": state.control_id,
                "cmmc_id": control.get("cmmc_id"),
                "name": control.get("name", ""),
                "family_abbr": control.get("family_abbr", ""),
                "weight": weight,
                "points_recoverable": deducted,
                "status": state.status,
                "objectives_outstanding": outstanding,
                "poam_allowed": bool(control.get("poam_allowed")),
                "reason": reason,
                "guidance": (control.get("guidance") or {}).get("summary", ""),
            }
        )
    actions.sort(
        key=lambda a: (-a["points_recoverable"], a["objectives_outstanding"], _sort_key(a["control_id"]))
    )
    return actions[:limit]


def _sort_key(identifier: str) -> tuple[int, ...]:
    """Sort 3.1.2 before 3.1.10 and 3.2.1."""
    try:
        return tuple(int(part) for part in identifier.split("."))
    except ValueError:
        return (999,)
