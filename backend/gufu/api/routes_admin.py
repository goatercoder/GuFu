from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query

from gufu.api.deps import get_state
from gufu.jobs.builder import Builder
from gufu.state import AppState

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/refresh")
async def refresh(kind: str = Query("all", pattern="^(all|facts|prices|metrics)$"), force: bool = False,
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
