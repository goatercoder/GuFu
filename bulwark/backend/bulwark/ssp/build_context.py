"""Assemble everything the SSP needs into one dictionary.

Every renderer (markdown, HTML, DOCX, JSON) consumes this same structure, so the document says
the same thing in every format.
"""

from __future__ import annotations

import json
from typing import Any

from sqlmodel import Session, select

from .. import catalog
from ..evidence_rules import agent_status
from ..models import (
    Asset,
    AssetCategory,
    CheckResult,
    ControlImplementation,
    Evidence,
    EvidenceLink,
    ObjectiveAssessment,
    Organization,
    PoamItem,
    PoamMilestone,
    PoamStatus,
    Provider,
    ResponsibilityRow,
    System,
    utcnow,
)

STATUS_LABELS = {
    "implemented": "Implemented",
    "partially_implemented": "Partially implemented",
    "planned": "Planned",
    "not_implemented": "Not implemented",
    "not_applicable": "Not applicable",
}

RESPONSIBILITY_LABELS = {
    "customer": "Organization",
    "provider": "Service provider",
    "shared": "Shared",
    "inherited": "Inherited from provider",
}

CATEGORY_LABELS = {
    AssetCategory.cui: "CUI Assets",
    AssetCategory.security_protection: "Security Protection Assets",
    AssetCategory.contractor_risk_managed: "Contractor Risk Managed Assets",
    AssetCategory.specialized: "Specialized Assets",
    AssetCategory.out_of_scope: "Out-of-scope Assets",
}

CATEGORY_DESCRIPTIONS = {
    AssetCategory.cui: "Process, store or transmit CUI. Assessed against all applicable requirements.",
    AssetCategory.security_protection: "Provide security functions for the CUI environment. Assessed "
    "against the requirements relevant to the security function they perform.",
    AssetCategory.contractor_risk_managed: "Not intended to handle CUI and are managed by risk-based "
    "policies and practices; documented but not assessed against every requirement.",
    AssetCategory.specialized: "Government property, internet-of-things, operational technology, "
    "restricted information systems and test equipment. Documented in the asset inventory and the SSP.",
    AssetCategory.out_of_scope: "Cannot process, store or transmit CUI and are physically or logically "
    "separated from the CUI environment.",
}


def _fmt_date(value) -> str:
    return value.strftime("%Y-%m-%d") if value else ""


def build_context(session: Session, system: System) -> dict[str, Any]:
    """Build the SSP context for one system."""
    from ..api.scoring import compute_score  # local import: avoids a circular import at module load

    org = session.exec(select(Organization).order_by(Organization.id)).first()
    score = compute_score(session, system.id)

    impls = {
        impl.control_id: impl
        for impl in session.exec(
            select(ControlImplementation).where(ControlImplementation.system_id == system.id)
        ).all()
    }
    objective_rows: dict[int, list[ObjectiveAssessment]] = {}
    if impls:
        for row in session.exec(
            select(ObjectiveAssessment).where(
                ObjectiveAssessment.implementation_id.in_([i.id for i in impls.values()])  # type: ignore[union-attr]
            )
        ).all():
            objective_rows.setdefault(row.implementation_id, []).append(row)

    providers = {p.id: p for p in session.exec(select(Provider)).all()}
    matrix: dict[tuple[int, str], ResponsibilityRow] = {
        (row.provider_id, row.control_id): row for row in session.exec(select(ResponsibilityRow)).all()
    }

    evidence_rows = list(session.exec(select(Evidence).where(Evidence.system_id == system.id)).all())
    evidence_by_id = {e.id: e for e in evidence_rows}
    evidence_by_control: dict[str, list[Evidence]] = {}
    if evidence_rows:
        for link in session.exec(
            select(EvidenceLink).where(
                EvidenceLink.evidence_id.in_(list(evidence_by_id))  # type: ignore[union-attr]
            )
        ).all():
            item = evidence_by_id.get(link.evidence_id)
            if item is not None:
                bucket = evidence_by_control.setdefault(link.control_id, [])
                if item not in bucket:
                    bucket.append(item)

    poam_items = list(session.exec(select(PoamItem).where(PoamItem.system_id == system.id)).all())
    milestones: dict[int, list[PoamMilestone]] = {}
    if poam_items:
        for milestone in session.exec(
            select(PoamMilestone).where(
                PoamMilestone.poam_item_id.in_([p.id for p in poam_items])  # type: ignore[union-attr]
            )
        ).all():
            milestones.setdefault(milestone.poam_item_id, []).append(milestone)
    poam_by_control: dict[str, list[PoamItem]] = {}
    for item in poam_items:
        poam_by_control.setdefault(item.control_id, []).append(item)

    assets = list(session.exec(select(Asset).where(Asset.system_id == system.id)).all())
    checks = {
        row.check_id: row
        for row in session.exec(
            select(CheckResult).where(
                CheckResult.system_id == system.id,
                CheckResult.is_latest == True,  # noqa: E712 - SQL boolean column comparison
            )
        ).all()
    }

    families = []
    for family in catalog.families():
        controls = []
        for control_id in family["control_ids"]:
            control = catalog.control(control_id) or {}
            impl = impls.get(control_id)
            provider = providers.get(impl.provider_id) if impl and impl.provider_id else None
            crm_row = matrix.get((provider.id, control_id)) if provider else None
            control_poam = poam_by_control.get(control_id, [])
            narrative = (impl.implementation_narrative or "").strip() if impl else ""
            if not narrative:
                if control_poam:
                    refs = ", ".join(f"POA&M-{p.id}" for p in control_poam)
                    narrative = f"NOT YET DOCUMENTED - tracked on the plan of action ({refs})."
                else:
                    narrative = (
                        "NOT YET DOCUMENTED - this requirement has no implementation statement and no "
                        "plan of action entry."
                    )
            objectives = []
            rows = {r.objective_id: r for r in objective_rows.get(impl.id, [])} if impl else {}
            for objective in control.get("objectives", []):
                row = rows.get(objective["id"])
                objectives.append(
                    {
                        "id": objective["id"],
                        "letter": objective["letter"],
                        "text": objective["text"],
                        "status": str(row.status) if row else "unknown",
                        "notes": (row.notes if row else "") or "",
                    }
                )
            controls.append(
                {
                    "id": control_id,
                    "cmmc_id": control.get("cmmc_id", ""),
                    "name": control.get("name", ""),
                    "weight": control.get("weight", 0),
                    "statement": control.get("statement", ""),
                    "discussion": control.get("discussion", ""),
                    "status": str(impl.status) if impl else "not_implemented",
                    "status_label": STATUS_LABELS.get(
                        str(impl.status) if impl else "not_implemented", "Not implemented"
                    ),
                    "responsibility": str(impl.responsibility) if impl else "customer",
                    "responsibility_label": RESPONSIBILITY_LABELS.get(
                        str(impl.responsibility) if impl else "customer", "Organization"
                    ),
                    "provider_name": provider.name if provider else "",
                    "provider_responsibility": (
                        (impl.provider_responsibility if impl else "")
                        or (crm_row.provider_responsibility if crm_row else "")
                        or ""
                    ),
                    "customer_responsibility": (
                        (impl.customer_responsibility if impl else "")
                        or (crm_row.customer_responsibility if crm_row else "")
                        or ""
                    ),
                    "inherited": bool(crm_row.inherited) if crm_row else False,
                    "narrative": narrative,
                    "na_justification": (impl.na_justification or "") if impl else "",
                    "partial_credit": str(impl.partial_credit) if impl else "none",
                    "assessed_by": (impl.assessed_by or "") if impl else "",
                    "assessed_at": _fmt_date(impl.assessed_at) if impl else "",
                    "objectives": objectives,
                    "evidence": [
                        {
                            "id": e.id,
                            "title": e.title,
                            "kind": str(e.kind),
                            "collected_at": _fmt_date(e.collected_at),
                            "file_name": e.file_name or "",
                            "source": str(e.source),
                        }
                        for e in evidence_by_control.get(control_id, [])
                    ],
                    "poam": [
                        {
                            "id": p.id,
                            "title": p.title,
                            "status": str(p.status),
                            "scheduled_completion": _fmt_date(p.scheduled_completion),
                        }
                        for p in control_poam
                    ],
                    "checks": [
                        {
                            "check_id": cid,
                            "status": checks[cid].status,
                            "observed": checks[cid].observed or "",
                        }
                        for cid in control.get("check_ids", [])
                        if cid in checks
                    ],
                }
            )
        families.append(
            {
                "id": family["id"],
                "abbr": family["abbr"],
                "name": family["name"],
                "controls": controls,
                "met": sum(1 for c in controls if c["status"] in ("implemented", "not_applicable")),
                "total": len(controls),
            }
        )

    asset_groups = []
    for category in AssetCategory:
        members = [a for a in assets if a.category == category]
        if not members and category == AssetCategory.out_of_scope:
            continue
        asset_groups.append(
            {
                "category": category.value,
                "label": CATEGORY_LABELS.get(category, category.value),
                "description": CATEGORY_DESCRIPTIONS.get(category, ""),
                "count": len(members),
                "assets": [
                    {
                        "name": a.name,
                        "type": str(a.asset_type),
                        "os": " ".join(filter(None, [a.os_name or "", a.os_version or ""])).strip(),
                        "ip_address": a.ip_address or "",
                        "location": a.location or "",
                        "owner": a.owner or "",
                        "rationale": a.category_rationale or "",
                        "agent_last_seen": _fmt_date(a.agent_last_seen),
                        "needs_review": a.needs_review,
                    }
                    for a in sorted(members, key=lambda x: x.name.lower())
                ],
            }
        )

    provider_summaries = []
    for provider in sorted(providers.values(), key=lambda p: p.name.lower()):
        rows = [row for (pid, _), row in matrix.items() if pid == provider.id]
        provider_summaries.append(
            {
                "name": provider.name,
                "kind": str(provider.kind),
                "service_description": provider.service_description or "",
                "fedramp_status": str(provider.fedramp_status),
                "crm_reference": provider.crm_reference or "",
                "contact": provider.contact or "",
                "rows_total": len(rows),
                "provider_rows": sum(1 for r in rows if str(r.model) == "provider"),
                "shared_rows": sum(1 for r in rows if str(r.model) == "shared"),
                "customer_rows": sum(1 for r in rows if str(r.model) == "customer"),
                "inherited_rows": sum(1 for r in rows if r.inherited),
            }
        )

    poam_summary = [
        {
            "id": item.id,
            "control_id": item.control_id,
            "cmmc_id": (catalog.control(item.control_id) or {}).get("cmmc_id", ""),
            "title": item.title,
            "weakness_description": item.weakness_description or "",
            "risk_level": str(item.risk_level),
            "status": str(item.status),
            "owner": item.owner or "",
            "identified_at": _fmt_date(item.identified_at),
            "scheduled_completion": _fmt_date(item.scheduled_completion),
            "actual_completion": _fmt_date(item.actual_completion),
            "milestones": [
                {
                    "description": m.description,
                    "due_date": _fmt_date(m.due_date),
                    "completed_at": _fmt_date(m.completed_at),
                }
                for m in sorted(milestones.get(item.id, []), key=lambda m: (m.position, m.id or 0))
            ],
        }
        for item in sorted(poam_items, key=lambda i: (i.status != PoamStatus.open, i.id or 0))
    ]

    agents = agent_status(session, system.id)
    meta = catalog.meta()
    now = utcnow()
    return {
        "generated_at": now.strftime("%Y-%m-%d %H:%M UTC"),
        "generated_date": now.strftime("%Y-%m-%d"),
        "document_version": f"{now:%Y.%m.%d}",
        "organization": {
            "name": org.name if org else "Organization not configured",
            "legal_name": (org.legal_name if org else "") or "",
            "cage_code": (org.cage_code if org else "") or "",
            "uei": (org.uei if org else "") or "",
            "address": ", ".join(
                filter(None, [org.address or "", org.city or "", org.state or "", org.zip or ""])
            )
            if org
            else "",
            "website": (org.website if org else "") or "",
            "industry": (org.industry if org else "") or "",
            "employee_count": (org.employee_count if org else None),
            "primary_contact": {
                "name": (org.primary_contact_name if org else "") or "",
                "email": (org.primary_contact_email if org else "") or "",
                "phone": (org.primary_contact_phone if org else "") or "",
            },
            "it_contact": {
                "name": (org.it_contact_name if org else "") or "",
                "email": (org.it_contact_email if org else "") or "",
                "phone": (org.it_contact_phone if org else "") or "",
            },
        },
        "system": {
            "id": system.id,
            "name": system.name,
            "description": system.description or "",
            "environment": str(system.environment),
            "boundary_description": system.boundary_description or "",
            "cui_types": system.cui_types or "",
            "cui_description": system.cui_description or "",
            "data_flow_description": system.data_flow_description or "",
            "status": str(system.status),
        },
        "score": score,
        "families": families,
        "asset_groups": asset_groups,
        "assets_total": len(assets),
        "providers": provider_summaries,
        "poam": poam_summary,
        "poam_open": sum(1 for p in poam_items if p.status in (PoamStatus.open, PoamStatus.in_progress)),
        "evidence": [
            {
                "id": e.id,
                "title": e.title,
                "kind": str(e.kind),
                "source": str(e.source),
                "collected_at": _fmt_date(e.collected_at),
                "expires_at": _fmt_date(e.expires_at),
                "file_name": e.file_name or "",
                "sha256": (e.sha256 or "")[:16],
            }
            for e in sorted(evidence_rows, key=lambda e: e.title.lower())
        ],
        "agents": agents,
        "catalog_meta": {
            "framework": meta.get("framework", ""),
            "assessment_procedures": meta.get("assessment_procedures", ""),
            "scoring": meta.get("scoring", ""),
            "attribution": meta.get("attribution", ""),
        },
        "status_labels": STATUS_LABELS,
    }


def context_json(context: dict[str, Any]) -> str:
    return json.dumps(context, indent=2, default=str)


__all__ = ["build_context", "context_json", "STATUS_LABELS", "CATEGORY_LABELS"]
