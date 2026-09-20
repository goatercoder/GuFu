"""Read-only access to the built catalog (``catalog/cmmc_l2_catalog.json``, ARCHITECTURE.md §2).

The file is parsed once per path and indexed for O(1) lookups. The path comes from
``Settings.catalog_path`` (override with ``BULWARK_CATALOG_PATH``).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from .config import get_settings

log = logging.getLogger(__name__)

_SUMMARY_OMIT = frozenset({"discussion", "assessment", "objectives", "guidance"})
_SAFE_TEMPLATE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


@dataclass
class Catalog:
    """Parsed catalog with lookup indexes."""

    meta: dict[str, Any]
    families: list[dict[str, Any]]
    controls: list[dict[str, Any]]
    checks: list[dict[str, Any]]
    _controls_by_id: dict[str, dict[str, Any]] = field(default_factory=dict, repr=False)
    _families_by_id: dict[str, dict[str, Any]] = field(default_factory=dict, repr=False)
    _checks_by_id: dict[str, dict[str, Any]] = field(default_factory=dict, repr=False)
    _objectives_by_id: dict[str, dict[str, Any]] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self._controls_by_id = {c["id"]: c for c in self.controls}
        self._families_by_id = {f["id"]: f for f in self.families}
        self._checks_by_id = {c["id"]: c for c in self.checks}
        for control in self.controls:
            for objective in control.get("objectives", []):
                self._objectives_by_id[objective["id"]] = objective

    # -- lookups ---------------------------------------------------------
    def control(self, control_id: str) -> dict[str, Any] | None:
        return self._controls_by_id.get(control_id)

    def family(self, family_id: str) -> dict[str, Any] | None:
        return self._families_by_id.get(family_id)

    def check(self, check_id: str) -> dict[str, Any] | None:
        return self._checks_by_id.get(check_id)

    def objective(self, objective_id: str) -> dict[str, Any] | None:
        return self._objectives_by_id.get(objective_id)

    @property
    def control_ids(self) -> list[str]:
        return [c["id"] for c in self.controls]

    @property
    def objective_ids(self) -> list[str]:
        return list(self._objectives_by_id.keys())


def _load_catalog_file(path: str) -> Catalog:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return Catalog(
        meta=raw.get("meta", {}),
        families=raw.get("families", []),
        controls=raw.get("controls", []),
        checks=raw.get("checks", []),
    )


@lru_cache(maxsize=4)
def _cached_catalog(path: str) -> Catalog:
    return _load_catalog_file(path)


def get_catalog() -> Catalog:
    """Return the catalog for the configured path (loaded once per path)."""
    return _cached_catalog(str(get_settings().catalog_path))


def clear_cache() -> None:
    _cached_catalog.cache_clear()


# --------------------------------------------------------------------------------------------
# Module-level convenience helpers (the names used across the codebase)
# --------------------------------------------------------------------------------------------
def meta() -> dict[str, Any]:
    return get_catalog().meta


def families() -> list[dict[str, Any]]:
    return get_catalog().families


def controls() -> list[dict[str, Any]]:
    return get_catalog().controls


def control(control_id: str) -> dict[str, Any] | None:
    """Full control record or ``None`` when the id is not in the catalog."""
    return get_catalog().control(control_id)


def control_ids() -> list[str]:
    return get_catalog().control_ids


def objectives_for(control_id: str) -> list[dict[str, Any]]:
    """Assessment objectives (``[{id, letter, text}]``) for a control; empty list if unknown."""
    ctrl = control(control_id)
    return list(ctrl.get("objectives", [])) if ctrl else []


def objective(objective_id: str) -> dict[str, Any] | None:
    return get_catalog().objective(objective_id)


def objective_ids_for(control_id: str) -> list[str]:
    return [o["id"] for o in objectives_for(control_id)]


def control_id_for_objective(objective_id: str) -> str:
    """``3.1.1[a]`` -> ``3.1.1``."""
    return objective_id.split("[", 1)[0]


def checks() -> list[dict[str, Any]]:
    return get_catalog().checks


def check(check_id: str) -> dict[str, Any] | None:
    return get_catalog().check(check_id)


def checks_for_control(control_id: str) -> list[dict[str, Any]]:
    return [c for c in checks() if control_id in c.get("control_ids", [])]


def check_summary(chk: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": chk["id"],
        "title": chk.get("title", chk["id"]),
        "kind": chk.get("kind"),
        "platforms": chk.get("platforms", []),
        "control_ids": chk.get("control_ids", []),
        "objective_ids": chk.get("objective_ids", []),
    }


def checks_summary() -> list[dict[str, Any]]:
    return [check_summary(c) for c in checks()]


def control_summary(control_id: str) -> dict[str, Any] | None:
    """Control without the long-form ``discussion``/``assessment``/``guidance`` text."""
    ctrl = control(control_id)
    if ctrl is None:
        return None
    summary = {k: v for k, v in ctrl.items() if k not in _SUMMARY_OMIT}
    summary["objective_count"] = len(ctrl.get("objectives", []))
    guidance = ctrl.get("guidance") or {}
    summary["guidance_summary"] = guidance.get("summary") or ""
    return summary


def controls_summary() -> list[dict[str, Any]]:
    return [s for s in (control_summary(c["id"]) for c in controls()) if s is not None]


def families_summary() -> list[dict[str, Any]]:
    return [
        {
            "id": f["id"],
            "abbr": f.get("abbr"),
            "name": f.get("name"),
            "control_ids": list(f.get("control_ids", [])),
            "control_count": len(f.get("control_ids", [])),
        }
        for f in families()
    ]


# --------------------------------------------------------------------------------------------
# Shared-responsibility (CRM) templates
# --------------------------------------------------------------------------------------------
def crm_templates_dir() -> Path:
    return Path(get_settings().crm_templates_dir)


def _read_template(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("Skipping unreadable CRM template %s: %s", path, exc)
        return None
    if not isinstance(data, dict):
        log.warning("Skipping CRM template %s: top level is not an object", path)
        return None
    data["id"] = path.stem
    data.setdefault("name", path.stem)
    data.setdefault("provider_kind", "other")
    data.setdefault("description", "")
    data.setdefault("rows", [])
    return data


def list_crm_templates() -> list[dict[str, Any]]:
    """``[{id, name, provider_kind, description}]`` for every readable template; ``[]`` if none."""
    directory = crm_templates_dir()
    if not directory.is_dir():
        return []
    result: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        data = _read_template(path)
        if data is None:
            continue
        result.append(
            {
                "id": data["id"],
                "name": data["name"],
                "provider_kind": data["provider_kind"],
                "description": data["description"],
            }
        )
    return result


def load_crm_template(template_id: str) -> dict[str, Any] | None:
    """Full template (with ``rows``) read from ``<dir>/<id>.json`` at call time, or ``None``."""
    if not _SAFE_TEMPLATE_ID.match(template_id or ""):
        return None
    path = crm_templates_dir() / f"{template_id}.json"
    if not path.is_file():
        return None
    return _read_template(path)
