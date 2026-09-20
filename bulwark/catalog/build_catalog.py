#!/usr/bin/env python3
"""Build catalog/cmmc_l2_catalog.json from the OSCAL source plus the enrichment files.

Deterministic and idempotent: run it after editing anything under enrichment/ or checks.json.
    python3 catalog/build_catalog.py            # writes cmmc_l2_catalog.json
    python3 catalog/build_catalog.py --check    # exit 1 if the committed file is stale
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "sources" / "nist-sp-800-171r2-combined-catalog.json"
ENRICH = HERE / "enrichment"
CHECKS = HERE / "checks.json"
OUT = HERE / "cmmc_l2_catalog.json"


def load_json(path: Path, default=None):
    if not path.exists():
        return default if default is not None else {}
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def prop(control: dict, name: str) -> str | None:
    for p in control.get("props", []):
        if p.get("name") == name:
            return p.get("value")
    return None


ARTIFACT = re.compile(r"\s*This publication is available free of charge from:?\s*(https?://\S*)?", re.I)


def clean_prose(text: str) -> str:
    """Remove the PDF running-footer artifact that leaked into a few objectives."""
    return ARTIFACT.sub("", text or "").strip()


def split_assessment(prose: str) -> dict:
    """'**EXAMINE:** [...]\n**INTERVIEW:** [...]\n**TEST:** [...]' -> dict."""
    out = {"examine": "", "interview": "", "test": ""}
    if not prose:
        return out
    parts = re.split(r"\*\*(EXAMINE|INTERVIEW|TEST):\*\*", prose)
    # parts: ['', 'EXAMINE', ' [..]\n', 'INTERVIEW', ' [..]', 'TEST', ' [..]']
    for i in range(1, len(parts) - 1, 2):
        key = parts[i].lower()
        text = clean_prose(parts[i + 1])
        text = re.sub(r"^\[SELECT FROM:\s*", "", text)
        text = re.sub(r"\]\.?$", "", text)
        out[key] = text.strip()
    return out


def build() -> dict:
    src = load_json(SOURCE)
    families_meta = load_json(ENRICH / "families.json")
    weights = load_json(ENRICH / "scoring_weights.json")
    names = load_json(ENRICH / "cmmc_names.json")
    nist53 = load_json(ENRICH / "nist80053_map.json")
    guidance = load_json(ENRICH / "guidance.json")
    claimed_weights: dict[str, int] = {}
    # Per-family enrichment files (catalog/enrichment/families/<family>.json) override the flat files.
    for fam_file in sorted((ENRICH / "families").glob("*.json")) if (ENRICH / "families").exists() else []:
        fam = load_json(fam_file)
        for cid, entry in fam.get("controls", {}).items():
            if entry.get("name"):
                names[cid] = entry["name"]
            if entry.get("nist_800_53"):
                nist53[cid] = entry["nist_800_53"]
            if entry.get("guidance"):
                guidance[cid] = entry["guidance"]
            if entry.get("weight_claimed") is not None:
                claimed_weights[cid] = entry["weight_claimed"]
    checks = load_json(CHECKS, default={"checks": []})
    check_list = checks.get("checks", checks if isinstance(checks, list) else [])

    five = set(weights.get("five_point", []))
    three = set(weights.get("three_point", []))
    unscored = set(weights.get("unscored", []))
    partial = weights.get("partial_credit", {})
    never_poam = set(weights.get("poam_never_allowed", []))

    checks_by_control: dict[str, list[str]] = {}
    for chk in check_list:
        for cid in chk.get("control_ids", []):
            checks_by_control.setdefault(cid, []).append(chk["id"])

    families = []
    controls = []
    for group in src["catalog"]["groups"]:
        fam_id = group["id"].replace("c-", "")
        meta = families_meta.get(fam_id, {})
        abbr = meta.get("abbr", fam_id)
        fam_name = meta.get("name", group["title"])
        fam_control_ids = []
        for ctl in group["controls"]:
            cid = prop(ctl, "label")
            fam_control_ids.append(cid)
            statement = discussion = assessment = ""
            objectives = []
            for part in ctl.get("parts", []):
                n = part.get("name")
                if n == "statement":
                    statement = clean_prose(part.get("prose", ""))
                elif n == "guidance":
                    discussion = clean_prose(part.get("prose", ""))
                elif n == "objective":
                    letter = part["id"].rsplit(".", 1)[-1]
                    objectives.append({"id": f"{cid}[{letter}]", "letter": letter,
                                       "text": clean_prose(part.get("prose", ""))})
                elif n == "assessment":
                    assessment = part.get("prose", "")
            if cid in unscored:
                weight = 0
            elif cid in five:
                weight = 5
            elif cid in three:
                weight = 3
            else:
                weight = 1
            pc = partial.get(cid)
            g = guidance.get(cid, {})
            controls.append({
                "id": cid,
                "cmmc_id": f"{abbr}.L2-{cid}",
                "family_id": fam_id,
                "family_abbr": abbr,
                "family_name": fam_name,
                "name": names.get(cid, ""),
                "requirement_type": prop(ctl, "requirement-type") or "",
                "statement": statement,
                "discussion": discussion,
                "objectives": objectives,
                "assessment": split_assessment(assessment),
                "weight": weight,
                "partial_credit": ({"deduction": pc["deduction_when_partial"], "condition": pc["condition"]}
                                   if pc else None),
                "poam_allowed": (weight == 1 and cid not in never_poam),
                "poam_never_allowed": cid in never_poam,
                "nist_800_53": nist53.get(cid, []),
                "guidance": {
                    "summary": g.get("summary", ""),
                    "machine_shop_example": g.get("machine_shop_example", ""),
                    "typical_evidence": g.get("typical_evidence", []),
                    "common_gaps": g.get("common_gaps", []),
                    "remediation_steps": g.get("remediation_steps", []),
                },
                "check_ids": sorted(checks_by_control.get(cid, [])),
                "_weight_claimed": claimed_weights.get(cid),
            })
        families.append({"id": fam_id, "abbr": abbr, "name": fam_name, "control_ids": fam_control_ids})

    return {
        "meta": {
            "framework": "NIST SP 800-171 Rev 2",
            "assessment_procedures": "NIST SP 800-171A",
            "cmmc_level": 2,
            "scoring": "NIST SP 800-171 DoD Assessment Methodology v1.2.1 / 32 CFR 170.24",
            "poam_rules": weights.get("poam_rules", {}),
            "source_catalog": src["catalog"]["metadata"],
            "attribution": "NIST SP 800-171 Rev 2 Combined OSCAL Catalog, Archstone Security LLC, "
                           "https://github.com/khanssen/oscal-nist-800-171r2 (CC BY 4.0); NIST text is public domain.",
        },
        "families": families,
        "controls": controls,
        "checks": check_list,
    }


def validate(cat: dict) -> list[str]:
    errors = []
    if len(cat["families"]) != 14:
        errors.append(f"expected 14 families, got {len(cat['families'])}")
    if len(cat["controls"]) != 110:
        errors.append(f"expected 110 controls, got {len(cat['controls'])}")
    n_obj = sum(len(c["objectives"]) for c in cat["controls"])
    if n_obj != 320:
        errors.append(f"expected 320 objectives, got {n_obj}")
    w = {5: 0, 3: 0, 1: 0, 0: 0}
    for c in cat["controls"]:
        w[c["weight"]] += 1
    if (w[5], w[3], w[1], w[0]) != (44, 14, 51, 1):
        errors.append(f"weight histogram 5/3/1/0 = {w[5]}/{w[3]}/{w[1]}/{w[0]}, expected 44/14/51/1")
    ids = {c["id"] for c in cat["controls"]}
    obj_ids = {o["id"] for c in cat["controls"] for o in c["objectives"]}
    for chk in cat["checks"]:
        for cid in chk.get("control_ids", []):
            if cid not in ids:
                errors.append(f"check {chk['id']} maps to unknown control {cid}")
        for oid in chk.get("objective_ids", []):
            if oid not in obj_ids:
                errors.append(f"check {chk['id']} maps to unknown objective {oid}")
    for c in cat["controls"]:
        claimed = c.get("_weight_claimed")
        if claimed is not None and claimed != c["weight"]:
            errors.append(f"{c['id']}: enrichment claims weight {claimed} but scoring_weights.json says {c['weight']}")
        if not c["name"]:
            errors.append(f"{c['id']}: missing CMMC practice name")
    seen = set()
    for chk in cat["checks"]:
        if chk["id"] in seen:
            errors.append(f"duplicate check id {chk['id']}")
        seen.add(chk["id"])
    return errors


def main(argv: list[str]) -> int:
    cat = build()
    errors = validate(cat)
    for c in cat["controls"]:
        c.pop("_weight_claimed", None)
    for e in errors:
        print("ERROR:", e, file=sys.stderr)
    text = json.dumps(cat, indent=1, ensure_ascii=False, sort_keys=False) + "\n"
    if "--check" in argv:
        if errors:
            return 1
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != text:
            print("cmmc_l2_catalog.json is stale; run python3 catalog/build_catalog.py", file=sys.stderr)
            return 1
        print("catalog up to date")
        return 0
    OUT.write_text(text, encoding="utf-8")
    n_obj = sum(len(c["objectives"]) for c in cat["controls"])
    print(f"wrote {OUT.name}: {len(cat['families'])} families, {len(cat['controls'])} controls, "
          f"{n_obj} objectives, {len(cat['checks'])} checks; {len(errors)} error(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
