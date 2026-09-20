"""FastAPI application factory and uvicorn entry point.

Routers are registered from the single ``ROUTERS`` list below; later stages append theirs
(``poam``, ``evidence``, ``agents``, ``scoring``, ``reports``, ``admin``) without touching
anything else here.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from . import __version__
from .api import (
    admin,
    agents,
    assets,
    auth,
    catalog,
    controls,
    evidence,
    organization,
    poam,
    providers,
    reports,
    scoring,
    systems,
)
from .auth import ensure_credentials
from .config import get_settings
from .db import init_db
from .schemas import HealthResponse

log = logging.getLogger(__name__)

ROUTERS: list[APIRouter] = [
    auth.router,
    catalog.router,
    organization.router,
    systems.router,
    assets.router,
    providers.router,
    controls.router,
    poam.router,
    evidence.router,
    agents.router,
    scoring.router,
    reports.router,
    admin.router,
]
"""Every router mounted under ``/api``. Later stages append to this list."""


class SPAStaticFiles(StaticFiles):
    """Serve the built frontend; unknown non-API paths fall back to ``index.html``."""

    async def get_response(self, path: str, scope) -> Response:  # noqa: ANN001
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or path == "api" or path.startswith("api/"):
                raise
            return await super().get_response("index.html", scope)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    ensure_credentials()
    settings = get_settings()
    log.info("Bulwark %s ready (data dir: %s)", __version__, settings.data_dir)
    yield


def create_app() -> FastAPI:
    """Build the application: routers under ``/api``, CORS for the Vite dev server, SPA at ``/``."""
    settings = get_settings()
    app = FastAPI(
        title="Bulwark",
        version=__version__,
        description="CMMC Level 2 / NIST SP 800-171 Rev 2 compliance automation",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.get("/api/health", response_model=HealthResponse, tags=["health"])
    def health() -> HealthResponse:
        return HealthResponse(status="ok", version=__version__)

    for router in ROUTERS:
        app.include_router(router, prefix="/api")

    dist = Path(settings.frontend_dist)
    if dist.is_dir() and (dist / "index.html").is_file():
        app.mount("/", SPAStaticFiles(directory=str(dist), html=True), name="frontend")
    else:
        log.info("Frontend build not found at %s; serving API only", dist)

    return app


app = create_app()


def run() -> None:
    """Start uvicorn on the configured host/port (``python -m bulwark``)."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    run()
