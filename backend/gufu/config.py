"""Runtime settings. All values can be overridden with GUFU_* environment variables."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GUFU_", env_file=REPO_DIR / ".env", extra="ignore")

    # SEC requires a descriptive User-Agent ("App name contact@email"). Requests without one get 403.
    sec_user_agent: str = ""
    # Serve everything from bundled fixtures + deterministic synthetic data (no network).
    fixture_mode: bool = False
    fixture_dir: Path = BACKEND_DIR / "fixtures"
    sp500_path: Path = REPO_DIR / "data" / "sp500.json"
    db_path: Path = BACKEND_DIR / "data" / "gufu.sqlite"
    keep_raw_facts: bool = True
    sec_rps: float = 8.0
    sec_concurrency: int = 6
    yahoo_concurrency: int = 3
    auto_build_on_start: bool = True
    facts_max_age_days: int = 7
    prices_max_age_hours: int = 24
    quote_ttl_seconds: int = 60
    frontend_dist: Path = REPO_DIR / "frontend" / "dist"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    def validate_runtime(self) -> None:
        if not self.fixture_mode and not self.sec_user_agent.strip():
            raise RuntimeError(
                "GUFU_SEC_USER_AGENT is required (e.g. 'GuFu research app you@example.com'). "
                "SEC EDGAR rejects requests without a descriptive User-Agent. "
                "Set GUFU_FIXTURE_MODE=1 to run offline on bundled sample data."
            )


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    global _settings
    _settings = None
