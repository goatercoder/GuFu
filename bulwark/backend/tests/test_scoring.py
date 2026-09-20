"""Scoring rules: ARCHITECTURE.md §5, 32 CFR 170.24 and 170.21."""

from __future__ import annotations

import pytest

from bulwark import catalog, scoring
from bulwark.scoring import ControlState


@pytest.fixture(scope="module")
def controls() -> list[dict]:
    return catalog.controls()


def states(overrides: dict[str, dict] | None = None, default: str = "implemented") -> list[ControlState]:
    """Every requirement at ``default`` except the ones named in ``overrides``."""
    overrides = overrides or {}
    out = []
    for control in catalog.controls():
        spec = overrides.get(control["id"], {})
        out.append(
            ControlState(
                control_id=control["id"],
                status=spec.get("status", default),
                partial_credit=spec.get("partial_credit", "none"),
                na_justification=spec.get("na_justification"),
                objective_statuses=spec.get("objective_statuses", {}),
            )
        )
    return out


def test_everything_implemented_scores_110(controls):
    result = scoring.score(states(), controls)
    assert result["sprs_score"] == 110
    assert result["met_count"] == 110
    assert result["not_met_count"] == 0
    assert result["final_ready"] is True
    assert result["conditional_eligible"] is True
    assert result["conditional_blockers"] == []


def test_nothing_implemented_scores_minus_203(controls):
    result = scoring.score(states(default="not_implemented"), controls)
    assert result["sprs_score"] == scoring.MIN_SCORE == -203
    assert result["assessment_blocked"] is True
    assert result["final_ready"] is False


def test_weights_match_the_dod_methodology(controls):
    """44 requirements deduct 5 points, 14 deduct 3 and 51 deduct 1; 3.12.4 deducts nothing."""
    histogram: dict[int, int] = {}
    for control in controls:
        histogram[control["weight"]] = histogram.get(control["weight"], 0) + 1
    assert histogram == {5: 44, 3: 14, 1: 51, 0: 1}
    assert sum(c["weight"] for c in controls) == 313


@pytest.mark.parametrize(
    ("control_id", "weight"),
    [("3.1.1", 5), ("3.1.5", 3), ("3.1.4", 1), ("3.5.3", 5), ("3.13.11", 5), ("3.14.5", 3)],
)
def test_single_gap_deducts_its_point_value(controls, control_id, weight):
    result = scoring.score(states({control_id: {"status": "not_implemented"}}), controls)
    assert result["sprs_score"] == 110 - weight
    assert result["deductions"][0]["control_id"] == control_id
    assert result["deductions"][0]["deducted"] == weight


def test_mfa_partial_credit_deducts_three_not_five(controls):
    partial = states({"3.5.3": {"status": "partially_implemented", "partial_credit": "mfa_partial"}})
    assert scoring.score(partial, controls)["sprs_score"] == 107
    full = states({"3.5.3": {"status": "not_implemented"}})
    assert scoring.score(full, controls)["sprs_score"] == 105


def test_non_fips_encryption_partial_credit_deducts_three(controls):
    partial = states(
        {"3.13.11": {"status": "partially_implemented", "partial_credit": "encryption_non_fips"}}
    )
    result = scoring.score(partial, controls)
    assert result["sprs_score"] == 107
    assert "FIPS" in result["deductions"][0]["reason"]


def test_partial_credit_only_applies_to_its_own_requirement(controls):
    """Claiming MFA partial credit on another requirement must not reduce its deduction."""
    result = scoring.score(
        states({"3.1.1": {"status": "partially_implemented", "partial_credit": "mfa_partial"}}), controls
    )
    assert result["sprs_score"] == 105


def test_missing_ssp_blocks_the_assessment_without_deducting(controls):
    result = scoring.score(states({"3.12.4": {"status": "not_implemented"}}), controls)
    assert result["sprs_score"] == 110
    assert result["assessment_blocked"] is True
    assert result["conditional_eligible"] is False
    assert any("system security plan" in blocker for blocker in result["conditional_blockers"])


def test_not_applicable_counts_as_met(controls):
    result = scoring.score(
        states({"3.13.14": {"status": "not_applicable", "na_justification": "No VoIP in use"}}), controls
    )
    assert result["sprs_score"] == 110
    assert result["na_count"] == 1
    assert result["warnings"] == []


def test_not_applicable_without_justification_warns(controls):
    result = scoring.score(states({"3.13.14": {"status": "not_applicable"}}), controls)
    assert result["sprs_score"] == 110
    assert result["warnings"][0]["control_id"] == "3.13.14"
    assert "justification" in result["warnings"][0]["messages"][0]


def test_implemented_with_a_failed_objective_is_downgraded(controls):
    """An assessor tests objectives, so a not-met objective overrides the claim."""
    result = scoring.score(
        states({"3.1.1": {"status": "implemented", "objective_statuses": {"3.1.1[a]": "not_met"}}}),
        controls,
    )
    assert result["sprs_score"] == 105
    assert result["warnings"][0]["control_id"] == "3.1.1"
    assert "3.1.1[a]" in result["warnings"][0]["messages"][0]


def test_unknown_objectives_do_not_downgrade(controls):
    result = scoring.score(
        states({"3.1.1": {"status": "implemented", "objective_statuses": {"3.1.1[a]": "unknown"}}}),
        controls,
    )
    assert result["sprs_score"] == 110


def test_conditional_eligibility_needs_88_points(controls):
    """Only 1-point gaps, and at least 88 points: 32 CFR 170.21(a)(2)."""
    one_pointers = [c["id"] for c in controls if c["weight"] == 1 and c["id"] not in scoring.NEVER_POAM]
    gaps = {cid: {"status": "not_implemented"} for cid in one_pointers[:22]}
    result = scoring.score(states(gaps), controls)
    assert result["sprs_score"] == 88
    assert result["conditional_eligible"] is True

    gaps = {cid: {"status": "not_implemented"} for cid in one_pointers[:23]}
    result = scoring.score(states(gaps), controls)
    assert result["sprs_score"] == 87
    assert result["conditional_eligible"] is False
    assert any("below the minimum" in b for b in result["conditional_blockers"])


def test_a_five_point_gap_blocks_conditional_status(controls):
    result = scoring.score(states({"3.1.1": {"status": "not_implemented"}}), controls)
    assert result["sprs_score"] == 105
    assert result["conditional_eligible"] is False
    assert any("more than 1 point" in b for b in result["conditional_blockers"])


def test_non_fips_encryption_may_remain_on_the_poam(controls):
    """3.13.11 at partial credit is the one exception to the 1-point rule."""
    result = scoring.score(
        states({"3.13.11": {"status": "partially_implemented", "partial_credit": "encryption_non_fips"}}),
        controls,
    )
    assert result["sprs_score"] == 107
    assert result["conditional_eligible"] is True


@pytest.mark.parametrize("control_id", scoring.NEVER_POAM)
def test_never_poam_requirements_block_conditional_status(controls, control_id):
    result = scoring.score(states({control_id: {"status": "not_implemented"}}), controls)
    assert result["conditional_eligible"] is False
    assert any("never sit on a POA&M" in b for b in result["conditional_blockers"])


def test_family_breakdown_sums_to_the_totals(controls):
    result = scoring.score(states({"3.1.1": {"status": "not_implemented"}}), controls)
    assert sum(f["total"] for f in result["families"]) == 110
    assert sum(f["met"] for f in result["families"]) == result["met_count"]
    assert sum(f["deducted_points"] for f in result["families"]) == 110 - result["sprs_score"]
    access_control = next(f for f in result["families"] if f["id"] == "3.1")
    assert access_control["abbr"] == "AC"
    assert access_control["total"] == 22


def test_status_histogram_counts_every_requirement(controls):
    result = scoring.score(
        states({"3.1.1": {"status": "planned"}, "3.1.2": {"status": "not_implemented"}}), controls
    )
    assert sum(result["by_status"].values()) == 110
    assert result["by_status"]["planned"] == 1


def test_readiness_percentage(controls):
    result = scoring.score(states({"3.1.1": {"status": "not_implemented"}}), controls)
    assert result["readiness_pct"] == pytest.approx(99.1, abs=0.1)


def test_next_actions_rank_by_points_then_objectives(controls):
    gaps = {
        "3.1.4": {"status": "not_implemented"},  # 1 point
        "3.1.1": {"status": "not_implemented"},  # 5 points
        "3.1.5": {"status": "not_implemented"},  # 3 points
    }
    actions = scoring.next_actions(states(gaps), controls, limit=5)
    assert [a["control_id"] for a in actions] == ["3.1.1", "3.1.5", "3.1.4"]
    assert actions[0]["points_recoverable"] == 5
    assert actions[0]["cmmc_id"] == "AC.L1-3.1.1"
    assert actions[0]["guidance"]


def test_next_actions_prefer_the_requirement_closest_to_done(controls):
    gaps = {
        "3.1.1": {"status": "not_implemented", "objective_statuses": {f"3.1.1[{x}]": "not_met"
                                                                     for x in "abcdef"}},
        "3.1.2": {"status": "not_implemented", "objective_statuses": {"3.1.2[a]": "not_met"}},
    }
    actions = scoring.next_actions(states(gaps), controls, limit=2)
    assert [a["control_id"] for a in actions] == ["3.1.2", "3.1.1"]


def test_next_actions_exclude_met_requirements(controls):
    assert scoring.next_actions(states(), controls, limit=10) == []


def test_score_is_stable_when_states_are_missing(controls):
    """A requirement with no row at all is treated as not implemented, not skipped."""
    partial_states = [s for s in states() if s.control_id != "3.1.1"]
    result = scoring.score(partial_states, controls)
    assert result["total"] == 110
    assert result["sprs_score"] == 105
