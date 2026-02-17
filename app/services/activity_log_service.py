"""Service helpers for creating generic activity log entries.

These helpers centralize how we persist audit trail information so that
routers and domain services can call a single function instead of
constructing ``ActivityLog`` rows directly.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.models.activity_log import ActivityLog, activity_log_actors


async def log_activity(
    db: AsyncSession,
    *,
    actor_id: int | None = None,
    actor_ids: list[int] | None = None,
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
        actor_id: Optional user id that performed the action (single actor).
        actor_ids: Optional list of user ids when multiple actors are
            involved (e.g. researchers on a visit).  When provided,
            ``actor_id`` is set to the first id for backward compatibility
            and all ids are linked via the ``activity_log_actors`` table.
        action: Machine-readable action label (e.g. ``"project_created"``).
        target_type: Logical target type (e.g. ``"project"``, ``"visit"``).
        target_id: Optional primary key of the affected entity.
        details: Optional JSON-serializable dict with extra context.
        batch_id: Optional correlation id for grouping related entries.
        commit: Whether to commit the session after inserting the log.

    Returns:
        The persisted ``ActivityLog`` instance.
    """

    effective_actor_id = actor_id
    if actor_ids and effective_actor_id is None:
        effective_actor_id = actor_ids[0]

    entry = ActivityLog(
        actor_id=effective_actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details or None,
        batch_id=batch_id,
    )
    db.add(entry)
    await db.flush()

    if actor_ids:
        await db.execute(
            insert(activity_log_actors),
            [{"activity_log_id": entry.id, "user_id": uid} for uid in actor_ids],
        )

    if commit:
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            logger.warning("Failed to commit activity log entry", exc_info=True)
            raise

    return entry
