from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from gufu.api.deps import get_state
from gufu.jobs.builder import Builder
from gufu.setup import apply_user_agent, build_user_agent, write_env_value
from gufu.state import AppState

router = APIRouter(prefix="/api/admin", tags=["admin"])
log = logging.getLogger("gufu.admin")


class SetupRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: str = Field(min_length=3, max_length=120)


@router.post("/setup")
async def setup(body: SetupRequest, state: AppState = Depends(get_state)):
    """One-time setup: SEC EDGAR requires a contact User-Agent on every request."""
    if state.fetchers.fixture:
        raise HTTPException(400, "Not applicable in sample-data mode")
    try:
        ua = build_user_agent(body.name, body.email)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    await apply_user_agent(state, ua)
    persisted = "db"
    try:
        write_env_value(state.settings.env_path, "GUFU_SEC_USER_AGENT", ua)
        persisted = "env"
    except OSError as exc:
        log.warning("could not write %s (%s); the value is kept in the database instead", state.settings.env_path, exc)
    return {"status": "ok", "user_agent": ua, "persisted": persisted, "setup_required": state.setup_required}


@router.post("/refresh")
async def refresh(kind: str = Query("all", pattern="^(all|facts|legacy|prices|metrics)$"), force: bool = False,
                  state: AppState = Depends(get_state)):
    if state.build_lock.locked():
        return {"status": "already_running", "job_id": state.current_job_id}
    task = asyncio.create_task(Builder(state).build_all(kind, force=force))
    state.background_tasks.add(task)
    task.add_done_callback(state.background_tasks.discard)
    await asyncio.sleep(0.05)
    return {"status": "started", "job_id": state.current_job_id}


@router.get("/jobs/latest")
def latest_job(state: AppState = Depends(get_state)):
    job = state.repo.latest_job()
    return job or {"status": "none"}


@router.get("/jobs/{job_id}")
def job(job_id: int, state: AppState = Depends(get_state)):
    j = state.repo.get_job(job_id)
    if not j:
        raise HTTPException(404, "no such job")
    return j
