"""Application settings.

Every setting can be overridden with an environment variable prefixed ``BULWARK_``
(for example ``BULWARK_DATA_DIR=/srv/bulwark/data``). Paths default to locations
resolved relative to this package so the app runs straight from a checkout.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = PACKAGE_DIR.parent
PROJECT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    """Runtime configuration (ARCHITECTURE.md §4.1)."""

    model_config = SettingsConfigDict(env_prefix="BULWARK_", extra="ignore", case_sensitive=False)

    # Storage -------------------------------------------------------------
    data_dir: Path = BACKEND_DIR / "data"
    """Directory holding bulwark.db, evidence/, secret.key and admin_password.txt."""

    catalog_path: Path = PROJECT_DIR / "catalog" / "cmmc_l2_catalog.json"
    """The built catalog. Overridable with BULWARK_CATALOG_PATH."""

    crm_templates_dir: Path = PROJECT_DIR / "catalog" / "enrichment" / "crm_templates"
    """Directory of shared-responsibility templates (``<id>.json``)."""

    frontend_dist: Path = PROJECT_DIR / "frontend" / "dist"
    """Built frontend, served at ``/`` with SPA fallback when present."""

    # Server --------------------------------------------------------------
    host: str = "127.0.0.1"
    port: int = 8800
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    server_url: str | None = None
    """Public URL agents should report to (used by the enrollment endpoint)."""

    # Security ------------------------------------------------------------
    admin_password: str | None = None
    """Admin password. When unset one is generated into data/admin_password.txt."""

    secret: str | None = None
    """Cookie signing secret. When unset one is generated into data/secret.key."""

    session_ttl_hours: int = 24 * 7

    # Behaviour -----------------------------------------------------------
    evidence_ttl_days: int = 30
    auto_poam: bool = True

    @property
    def db_path(self) -> Path:
        return self.data_dir / "bulwark.db"

    @property
    def evidence_dir(self) -> Path:
        return self.data_dir / "evidence"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings (cached; call ``get_settings.cache_clear()`` in tests)."""
    return Settings()
