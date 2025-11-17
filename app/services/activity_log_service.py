from __future__ import annotations

"""Service helpers for creating generic activity log entries.

These helpers centralize how we persist audit trail information so that
routers and domain services can call a single function instead of
constructing ``ActivityLog`` rows directly.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.models.visit_log import ActivityLog


async def log_activity(
    db: AsyncSession,
    *,
    actor_id: int | None,
    action: str,
    target_type: str,
    target_id: int | None = None,
    details: dict[str, Any] | None = None,
    batch_id: str | None = None,
    commit: bool = True,
) -> ActivityLog:
    """Create and persist a single ``ActivityLog`` entry.

    Args:
        db: Async SQLAlchemy session.
        actor_id: Optional user id that performed the action.
        action: Machine-readable action label (e.g. ``"project_created"``).
        target_type: Logical target type (e.g. ``"project"``, ``"visit"``).
        target_id: Optional primary key of the affected entity.
        details: Optional JSON-serializable dict with extra context.
        batch_id: Optional correlation id for grouping related entries.
        commit: Whether to commit the session after inserting the log.

    Returns:
        The persisted ``ActivityLog`` instance.
    """

    entry = ActivityLog(
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details or None,
        batch_id=batch_id,
    )
    db.add(entry)

    if commit:
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            logger.warning("Failed to commit activity log entry", exc_info=True)
            raise

    return entry
