"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from gufu.api import routes_admin, routes_companies, routes_home, routes_screener
from gufu.config import Settings, get_settings
from gufu.fetch.fixtures import make_fetchers
from gufu.jobs.scheduler import scheduler_loop
from gufu.services.screener_service import rebuild_screener
from gufu.state import AppState
from gufu.store.db import Database
from gufu.store.repo import Repo
from gufu.universe import load_sp500

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("gufu")


def build_state(settings: Settings) -> AppState:
    db = Database(settings.db_path)
    repo = Repo(db)
    if settings.setup_required:
        # Precedence: GUFU_SEC_USER_AGENT env var > .env file > value saved by the in-app setup screen.
        settings.sec_user_agent = repo.kv_get("sec_user_agent") or ""
    profiles = load_sp500(settings.sp500_path)
    cached = {p.ticker: p for p in repo.get_companies()}
    merged = []
    for p in profiles:
        c = cached.get(p.ticker)
        merged.append(type(p)(p.ticker, p.name, p.sector, p.sub_industry, p.cik or (c.cik if c else None)))
    state = AppState(settings=settings, db=db, repo=repo, fetchers=make_fetchers(settings), profiles=merged)
    state.profile_by_ticker = {p.ticker: p for p in merged}
    if not state.setup_required:
        state.setup_done.set()
    repo.upsert_companies(merged)
    rebuild_screener(state)
    return state


def create_app(settings: Settings | None = None, run_scheduler: bool = True) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        state = build_state(settings)
        app.state.gufu = state
        log.info("GuFu starting: %d companies, fixture_mode=%s, setup_required=%s, db=%s", len(state.profiles),
                 settings.fixture_mode, state.setup_required, settings.db_path)
        if state.setup_required:
            log.info("Waiting for one-time setup: open the app in your browser and enter your name and email.")
        task = asyncio.create_task(scheduler_loop(state)) if run_scheduler else None
        try:
            yield
        finally:
            if task:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass
            await state.fetchers.close()
            state.db.close()

    app = FastAPI(title="GuFu", version="0.1.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])
    app.include_router(routes_home.router)
    app.include_router(routes_companies.router)
    app.include_router(routes_screener.router)
    app.include_router(routes_admin.router)

    dist = settings.frontend_dist
    if dist.exists() and (dist / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            candidate = dist / path
            if path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")

    return app


app = create_app()
