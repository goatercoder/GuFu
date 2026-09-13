from __future__ import annotations

from fastapi import APIRouter, Depends

from gufu.api.deps import get_state
from gufu.services.screener_service import home_summary
from gufu.state import AppState

router = APIRouter(prefix="/api", tags=["home"])


@router.get("/home")
def home(state: AppState = Depends(get_state)):
    return home_summary(state, len(state.profiles))


@router.get("/health")
def health(state: AppState = Depends(get_state)):
    return {
        "status": "ok", "fixture_mode": state.fetchers.fixture, "setup_required": state.setup_required,
        "companies": len(state.profiles),
        "metrics_cached": state.repo.count_metrics(), "legacy_cached": state.repo.count_legacy(), "screener_built_at": state.screener_built_at,
        "last_facts_build": state.repo.kv_get("last_facts_build"), "last_prices_build": state.repo.kv_get("last_prices_build"),
        "building": state.build_lock.locked(), "current_job_id": state.current_job_id,
    }
