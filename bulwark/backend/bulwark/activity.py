"""Activity log helper: every write in the API records one row."""

from __future__ import annotations

from sqlmodel import Session

from .models import ActivityLog

MAX_SUMMARY = 500


def log_activity(
    session: Session,
    actor: str,
    action: str,
    entity_type: str,
    entity_id: int | None,
    summary: str,
    *,
    system_id: int | None = None,
) -> ActivityLog:
    """Add an ``activity_log`` row to the session (the caller commits).

    ``action`` is a short verb (``create``/``update``/``delete``/``login``...), ``entity_type`` the
    table or concept touched (``system``, ``control_implementation``...). Never put secrets
    (passwords, enrollment keys) into ``summary``.
    """
    entry = ActivityLog(
        system_id=system_id,
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary[:MAX_SUMMARY],
    )
    session.add(entry)
    return entry
