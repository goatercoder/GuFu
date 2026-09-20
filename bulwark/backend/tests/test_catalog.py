"""Catalog integrity (ARCHITECTURE.md §9) and the /api/catalog routes."""

from __future__ import annotations

from collections import Counter

import pytest
from fastapi.testclient import TestClient

from bulwark import catalog


@pytest.fixture
def cat(env):  # noqa: ANN001
    return catalog.get_catalog()


def test_counts(cat) -> None:  # noqa: ANN001
    assert len(cat.families) == 14
    assert len(cat.controls) == 110
    assert sum(len(c["objectives"]) for c in cat.controls) == 320
    assert len(cat.objective_ids) == 320
    assert len(catalog.control_ids()) == 110


def test_weight_histogram(cat) -> None:  # noqa: ANN001
    histogram = Counter(c["weight"] for c in cat.controls)
    assert histogram == {5: 44, 3: 14, 1: 51, 0: 1}
    assert catalog.control("3.12.4")["weight"] == 0
    assert sum(c["weight"] for c in cat.controls) == 313


def test_partial_credit_and_poam_rules(cat) -> None:  # noqa: ANN001
    partial = sorted(c["id"] for c in cat.controls if c["partial_credit"])
    assert partial == ["3.13.11", "3.5.3"]
    assert catalog.control("3.5.3")["partial_credit"]["deduction"] == 3
    never = sorted(c["id"] for c in cat.controls if c.get("poam_never_allowed"))
    assert never == sorted(["3.1.20", "3.1.22", "3.10.3", "3.10.4", "3.10.5"])
    for ctrl in cat.controls:
        if ctrl["poam_allowed"]:
            assert ctrl["weight"] == 1 and not ctrl.get("poam_never_allowed")


def test_families_cover_controls_exactly_once(cat) -> None:  # noqa: ANN001
    ids = [cid for family in cat.families for cid in family["control_ids"]]
    assert len(ids) == 110
    assert set(ids) == set(catalog.control_ids())
    for family in cat.families:
        for cid in family["control_ids"]:
            assert catalog.control(cid)["family_id"] == family["id"]


def test_ids_use_canonical_forms(cat) -> None:  # noqa: ANN001
    for ctrl in cat.controls:
        assert ctrl["id"].startswith("3.")
        assert ctrl["cmmc_id"].endswith(ctrl["id"])
        for objective in ctrl["objectives"]:
            assert objective["id"].startswith(ctrl["id"] + "[")
            assert objective["id"].endswith("]")
            assert catalog.control_id_for_objective(objective["id"]) == ctrl["id"]


def test_every_check_maps_to_real_controls_and_objectives(cat) -> None:  # noqa: ANN001
    assert cat.checks, "check catalog is empty"
    seen: set[str] = set()
    for chk in cat.checks:
        assert chk["id"] not in seen
        seen.add(chk["id"])
        assert chk["control_ids"], chk["id"]
        for cid in chk["control_ids"]:
            assert catalog.control(cid) is not None, (chk["id"], cid)
        for oid in chk["objective_ids"]:
            assert catalog.objective(oid) is not None, (chk["id"], oid)
            assert catalog.control_id_for_objective(oid) in chk["control_ids"], (chk["id"], oid)
        scope = chk["id"].split(".")[0]
        assert scope in {"os", "win", "nix", "mac"}
    # reverse mapping in the controls is consistent with checks.json
    for ctrl in cat.controls:
        for check_id in ctrl["check_ids"]:
            assert ctrl["id"] in catalog.check(check_id)["control_ids"]


def test_summary_helpers_omit_long_text(env) -> None:  # noqa: ANN001
    summary = catalog.control_summary("3.1.1")
    assert summary is not None
    assert "discussion" not in summary and "assessment" not in summary
    assert summary["objective_count"] == 6
    assert catalog.control_summary("nope") is None
    assert catalog.objectives_for("nope") == []
    assert len(catalog.objectives_for("3.1.1")) == 6
    families = catalog.families_summary()
    assert families[0]["abbr"] == "AC" and families[0]["control_count"] == 22
    assert catalog.checks_for_control("3.1.1")
    assert catalog.list_crm_templates() == []
    assert catalog.load_crm_template("../etc/passwd") is None


def test_catalog_path_override(tmp_path, monkeypatch, env) -> None:  # noqa: ANN001
    import json

    from bulwark.config import get_settings

    path = tmp_path / "mini.json"
    path.write_text(json.dumps({"meta": {}, "families": [], "controls": [], "checks": []}))
    monkeypatch.setenv("BULWARK_CATALOG_PATH", str(path))
    get_settings.cache_clear()
    catalog.clear_cache()
    assert catalog.controls() == []


# --------------------------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------------------------
def test_catalog_endpoint_shape(client: TestClient) -> None:
    response = client.get("/api/catalog")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"meta", "families", "controls", "checks"}
    assert len(body["families"]) == 14
    assert len(body["controls"]) == 110
    assert len(body["checks"]) == len(catalog.checks())
    first = body["controls"][0]
    assert first["id"] == "3.1.1"
    assert "discussion" not in first and "assessment" not in first
    assert first["weight"] == 5 and first["objective_count"] == 6
    assert body["families"][0]["control_ids"][0] == "3.1.1"
    assert {"id", "title", "kind", "platforms", "control_ids", "objective_ids"} <= set(body["checks"][0])


def test_catalog_control_detail(client: TestClient) -> None:
    response = client.get("/api/catalog/controls/3.1.1")
    assert response.status_code == 200
    body = response.json()
    assert body["discussion"]
    assert len(body["objectives"]) == 6
    assert body["objectives"][0]["id"] == "3.1.1[a]"
    assert set(body["assessment"]) == {"examine", "interview", "test"}
    assert "guidance" in body
    missing = client.get("/api/catalog/controls/9.9.9")
    assert missing.status_code == 404
    assert "9.9.9" in missing.json()["detail"]


def test_catalog_checks_and_templates(client: TestClient) -> None:
    checks = client.get("/api/catalog/checks")
    assert checks.status_code == 200
    assert len(checks.json()) == len(catalog.checks())
    assert checks.json()[0]["id"] == catalog.checks()[0]["id"]
    templates = client.get("/api/catalog/crm-templates")
    assert templates.status_code == 200
    assert templates.json() == []
