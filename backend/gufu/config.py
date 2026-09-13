"""Runtime settings. All values can be overridden with GUFU_* environment variables."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GUFU_", env_file=REPO_DIR / ".env", extra="ignore")

    # SEC requires a descriptive User-Agent ("App name contact@email"). Requests without one get 403.
    # A preset contact is built in so nothing has to be configured; override with GUFU_SEC_USER_AGENT.
    sec_user_agent: str = "GuFu/0.1 (John; johndoe@gmail.com)"
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
    # Pre-2009 history from old 10-K filings ("Selected Financial Data" + statements)
    legacy_enabled: bool = True
    legacy_max_filings: int = 6
    legacy_on_demand_timeout: float = 45.0
    # Prebuilt nightly dataset (built by GitHub Actions). Empty string disables the download.
    dataset_url: str = "https://github.com/goatercoder/GuFu/releases/download/data-latest/gufu-data.sqlite.gz"
    frontend_dist: Path = REPO_DIR / "frontend" / "dist"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    # Where the in-app setup screen persists the SEC User-Agent.
    env_path: Path = REPO_DIR / ".env"

    @property
    def setup_required(self) -> bool:
        """Live mode cannot talk to SEC EDGAR until a contact User-Agent has been provided."""
        return not self.fixture_mode and not self.sec_user_agent.strip()


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    global _settings
    _settings = None
