"""POA&M export and the assessment-readiness report."""

from __future__ import annotations

import csv
import io
from typing import Any

from sqlmodel import Session, select

from . import catalog
from .models import PoamMilestone, PoamStatus, System
from .ssp.render import markdown_to_html, render_docx, render_html

POAM_COLUMNS = [
    "POA&M ID",
    "Weakness",
    "Weakness description",
    "Security requirement",
    "CMMC practice",
    "Point value",
    "Source",
    "Risk level",
    "Status",
    "Owner",
    "Identified",
    "Scheduled completion",
    "Actual completion",
    "Milestones",
    "Resources required",
    "Estimated cost",
    "Notes",
]


def _milestone_text(milestones: list[PoamMilestone]) -> str:
    parts = []
    for milestone in sorted(milestones, key=lambda m: (m.position, m.id or 0)):
        text = milestone.description
        if milestone.due_date:
            text += f" (due {milestone.due_date.isoformat()})"
        if milestone.completed_at:
            text += f" [completed {milestone.completed_at.date().isoformat()}]"
        parts.append(text)
    return " | ".join(parts)


def poam_rows(session: Session, system: System) -> list[dict[str, Any]]:
    """The POA&M register in the column order DoD assessors expect."""
    from .models import PoamItem  # local import keeps the module import graph flat

    items = list(session.exec(select(PoamItem).where(PoamItem.system_id == system.id)).all())
    milestones: dict[int, list[PoamMilestone]] = {}
    if items:
        for milestone in session.exec(
            select(PoamMilestone).where(
                PoamMilestone.poam_item_id.in_([i.id for i in items])  # type: ignore[union-attr]
            )
        ).all():
            milestones.setdefault(milestone.poam_item_id, []).append(milestone)

    rows = []
    for item in sorted(items, key=lambda i: (i.status != PoamStatus.open, i.id or 0)):
        control = catalog.control(item.control_id) or {}
        rows.append(
            {
                "POA&M ID": f"POA&M-{item.id}",
                "Weakness": item.title,
                "Weakness description": item.weakness_description or "",
                "Security requirement": item.control_id,
                "CMMC practice": control.get("cmmc_id", ""),
                "Point value": control.get("weight", ""),
                "Source": str(item.source),
                "Risk level": str(item.risk_level),
                "Status": str(item.status),
                "Owner": item.owner or "",
                "Identified": item.identified_at.isoformat() if item.identified_at else "",
                "Scheduled completion": (
                    item.scheduled_completion.isoformat() if item.scheduled_completion else ""
                ),
                "Actual completion": (
                    item.actual_completion.isoformat() if item.actual_completion else ""
                ),
                "Milestones": _milestone_text(milestones.get(item.id, [])),
                "Resources required": item.resources_required or "",
                "Estimated cost": item.cost_estimate or "",
                "Notes": (item.notes or "").replace("\n", " / "),
            }
        )
    return rows


def poam_csv(session: Session, system: System) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=POAM_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(poam_rows(session, system))
    return buffer.getvalue()


def _escape_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def poam_markdown(session: Session, system: System, organization_name: str) -> str:
    rows = poam_rows(session, system)
    lines = [
        "# Plan of Action and Milestones",
        "",
        f"**{organization_name}** - system **{system.name}**",
        "",
        f"{len(rows)} item(s) recorded."
        if rows
        else "_No plan of action entries are recorded for this system._",
        "",
    ]
    if rows:
        header = [
            "POA&M ID",
            "Security requirement",
            "CMMC practice",
            "Point value",
            "Weakness",
            "Risk level",
            "Status",
            "Owner",
            "Identified",
            "Scheduled completion",
        ]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("|" + "---|" * len(header))
        for row in rows:
            lines.append("| " + " | ".join(_escape_cell(row[column]) for column in header) + " |")
        lines.append("")
        for row in rows:
            lines.append(f"## {row['POA&M ID']} - {row['Weakness']}")
            lines.append("")
            lines.append(f"**Requirement.** {row['CMMC practice'] or row['Security requirement']} "
                         f"({row['Point value']} points)")
            lines.append("")
            if row["Weakness description"]:
                lines.append(f"**Weakness.** {row['Weakness description']}")
                lines.append("")
            if row["Milestones"]:
                lines.append("**Milestones**")
                lines.append("")
                for part in row["Milestones"].split(" | "):
                    lines.append(f"1. {part}")
                lines.append("")
            if row["Resources required"]:
                lines.append(f"**Resources.** {row['Resources required']}")
                lines.append("")
            if row["Notes"]:
                lines.append(f"**Notes.** {row['Notes']}")
                lines.append("")
    return "\n".join(lines) + "\n"


def readiness_markdown(context: dict[str, Any]) -> str:
    """Executive readiness summary: score, blockers, families, next actions, findings."""
    score = context["score"]
    system = context["system"]
    organization = context["organization"]
    readiness = context["readiness"]
    lines = [
        "# CMMC Level 2 assessment readiness",
        "",
        f"**{organization['name']}** - system **{system['name']}**",
        "",
        f"Generated {context['generated_at']}",
        "",
        "## Summary",
        "",
        "| | |",
        "|---|---|",
        f"| SPRS score | **{score['sprs_score']}** of {score['max_score']} "
        f"(minimum possible {score['min_score']}) |",
        f"| Requirements met | {score['met_count']} of {score['total']} "
        f"({score['readiness_pct']}%) |",
        f"| Not applicable | {score['na_count']} |",
        f"| Conditional certification eligible | "
        f"{'Yes' if score['conditional_eligible'] else 'No'} |",
        f"| Ready for final certification | {'Yes' if score['final_ready'] else 'No'} |",
        f"| Evidence coverage (objectives) | {readiness['evidence_coverage']['pct']}% "
        f"({readiness['evidence_coverage']['covered']} of "
        f"{readiness['evidence_coverage']['total']}) |",
        f"| Automated coverage (requirements with a passing check) | "
        f"{readiness['automated_coverage']['pct']}% |",
        f"| Open POA&M items | {readiness['open_poam_count']} "
        f"({readiness['overdue_poam_count']} overdue, {readiness['aging_poam_count']} over 180 days) |",
        f"| Failing automated checks | {readiness['findings_count']} |",
        f"| Endpoints reporting | {readiness['agents_reporting']} "
        f"({readiness['agents_stale']} stale) |",
        "",
    ]
    if score["assessment_blocked"]:
        lines += [
            "> **The assessment cannot be completed.** Requirement 3.12.4 (system security plan) "
            "is not implemented.",
            "",
        ]
    if score["conditional_blockers"]:
        lines += ["## What blocks a Conditional CMMC Status", ""]
        lines += [f"- {blocker}" for blocker in score["conditional_blockers"]]
        lines.append("")
    lines += ["## Progress by family", "", "| Family | Met | Total | Points deducted |", "|---|---|---|---|"]
    for family in score["families"]:
        lines.append(
            f"| {family['abbr']} - {family['name']} | {family['met']} | {family['total']} | "
            f"{family['deducted_points']} |"
        )
    lines.append("")
    if readiness["next_actions"]:
        lines += [
            "## Next actions",
            "",
            "| Requirement | Practice | Points recoverable | Status | Objectives outstanding |",
            "|---|---|---|---|---|",
        ]
        for action in readiness["next_actions"]:
            lines.append(
                f"| {action['cmmc_id'] or action['control_id']} | {action['name']} | "
                f"{action['points_recoverable']} | {action['status']} | "
                f"{action['objectives_outstanding']} |"
            )
        lines.append("")
    if readiness.get("contradiction_count"):
        lines += [
            "## Requirements contradicted by live endpoint data",
            "",
            f"{readiness['contradiction_count']} requirement(s) are recorded as met while an "
            "automated check on an in-scope asset is failing. An assessor will test the objective, "
            "not the claim.",
            "",
            "| Requirement | Practice | Points at risk | Recorded as | Failing checks |",
            "|---|---|---|---|---|",
        ]
        for item in readiness["contradictions"]:
            lines.append(
                f"| {item['cmmc_id'] or item['control_id']} | {item['name']} | {item['weight']} | "
                f"{item['recorded_status']} | {', '.join(item['failing_checks'])} |"
            )
        lines.append("")
    if readiness["inheritance_gaps"]:
        lines += ["## Shared responsibility gaps", ""]
        lines += [f"- {gap}" for gap in readiness["inheritance_gaps"]]
        lines.append("")
    if context.get("findings"):
        lines += [
            "## Failing automated checks",
            "",
            "| Requirement | Check | Assets affected | Expected |",
            "|---|---|---|---|",
        ]
        for finding in context["findings"][:30]:
            lines.append(
                f"| {finding['cmmc_id'] or finding['control_id']} | {finding['check_title']} | "
                f"{finding['asset_count']} | {_escape_cell(finding['expected'] or '')} |"
            )
        lines.append("")
    if score["warnings"]:
        lines += ["## Consistency warnings", ""]
        for warning in score["warnings"][:20]:
            for message in warning["messages"]:
                lines.append(f"- **{warning['control_id']}**: {message}")
        lines.append("")
    lines += [
        "---",
        "",
        "_Generated by Bulwark from the live compliance record. Scoring follows the NIST SP 800-171 "
        "DoD Assessment Methodology as carried into 32 CFR 170.24; eligibility rules follow "
        "32 CFR 170.21._",
    ]
    return "\n".join(lines) + "\n"


def markdown_to_docx(markdown_text: str) -> bytes:
    """Reuse the SSP DOCX writer for any Markdown document."""
    return render_docx({"_markdown": markdown_text}, template="__inline__")


__all__ = [
    "POAM_COLUMNS",
    "poam_rows",
    "poam_csv",
    "poam_markdown",
    "readiness_markdown",
    "markdown_to_html",
    "render_html",
    "markdown_to_docx",
]
