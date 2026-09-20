"""SQLite engine, session dependency and schema initialisation."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from .config import get_settings

_engine: Engine | None = None


def _apply_sqlite_pragmas(dbapi_connection, _connection_record) -> None:  # noqa: ANN001
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=5000")
    finally:
        cursor.close()


def get_engine() -> Engine:
    """Return the shared engine, creating it (and the data directory) on first use."""
    global _engine
    if _engine is None:
        settings = get_settings()
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        engine = create_engine(
            settings.database_url,
            connect_args={"check_same_thread": False},
            echo=False,
        )
        event.listen(engine, "connect", _apply_sqlite_pragmas)
        _engine = engine
    return _engine


def reset_engine() -> None:
    """Dispose the cached engine so the next call to ``get_engine`` re-reads settings (tests)."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


def init_db() -> None:
    """Create the data directory and every table declared in :mod:`bulwark.models`."""
    from . import models  # noqa: F401  (registers the tables on SQLModel.metadata)

    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.evidence_dir.mkdir(parents=True, exist_ok=True)
    SQLModel.metadata.create_all(get_engine())


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a database session."""
    with Session(get_engine()) as session:
        yield session
