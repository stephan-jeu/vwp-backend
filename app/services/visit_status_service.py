"""Helpers for deriving visit lifecycle status from logs and visit data.

This module centralizes the logic that combines persisted visit fields
(e.g. date window and assigned researchers) with the latest relevant
``ActivityLog`` entry for that visit to derive a simple status code.

The status codes are intentionally internal English labels; the
frontend is responsible for mapping them to Dutch UI strings.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import logger
from app.models.visit import Visit
from app.models.activity_log import ActivityLog


class VisitStatusCode(StrEnum):
    """Machine-readable lifecycle status for a visit.

    Values are kept generic and English; mapping to Dutch labels should
    be done in the frontend.

    Rough mapping to business concepts:

    * ``created``  – visit exists but has no concrete date window.
    * ``open``     – has a date window but no assigned researchers yet
                     and the window has not expired.
    * ``planned``  – at least one researcher is assigned for the visit.
    * ``overdue``  – visit window is in the past without an execution
                     / cancellation / approval log.
    * ``executed`` – executed according to protocol.
    * ``executed_with_deviation`` – executed with a deviation log.
    * ``not_executed`` – explicitly logged as not executed.
    * ``missed`` – derived status if researchers assigned but week number is in the past.
    * ``approved`` – result explicitly approved.
    * ``rejected`` – result explicitly rejected.
    * ``cancelled`` – visit was cancelled.
    """

    CREATED = "created"
    OPEN = "open"
    PLANNED = "planned"
    OVERDUE = "overdue"
    EXECUTED = "executed"
    EXECUTED_WITH_DEVIATION = "executed_with_deviation"
    NOT_EXECUTED = "not_executed"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    MISSED = "missed"


# ActivityLog.action values that influence lifecycle status, ordered by
# decreasing precedence (later entries in time always win, but this
# list documents which actions are considered status-bearing).
_STATUS_ACTIONS: set[str] = {
    "visit_executed",
    "visit_executed_deviation",
    "visit_executed_with_deviation",
    "visit_not_executed",
    "visit_approved",
    "visit_rejected",
    "visit_cancelled",
    "visit_status_cleared",
}


async def _latest_status_log_for_visit(
    db: AsyncSession,
    visit_id: int,
) -> ActivityLog | None:
    """Return the most recent status-bearing ActivityLog for a visit.

    Args:
        db: Async SQLAlchemy session.
        visit_id: Primary key of the visit.

    Returns:
        The latest ``ActivityLog`` row for the visit whose ``action`` is
        in the known status-bearing set, or ``None`` if none exist.
    """

    stmt: Select[tuple[ActivityLog]] = (
        select(ActivityLog)
        .where(
            ActivityLog.target_type == "visit",
            ActivityLog.target_id == visit_id,
            ActivityLog.action.in_(_STATUS_ACTIONS),
        )
        .order_by(ActivityLog.created_at.desc())
        .limit(1)
    )

    row = (await db.execute(stmt)).scalars().first()
    return row


def derive_visit_status(
    visit: Visit,
    last_log: ActivityLog | None,
    *,
    today: date | None = None,
) -> VisitStatusCode:
    """Derive the lifecycle status for a visit.

    This function is pure and side-effect free; it does not perform any
    I/O. When a status-bearing log entry is present for the visit, that
    log takes precedence. Otherwise the status is derived from the visit
    dates and assigned researchers.

    Args:
        visit: Visit ORM instance with at least ``from_date``,
            ``to_date`` and ``researchers`` populated.
        last_log: Most recent status-bearing ``ActivityLog`` for the
            visit, or ``None`` when no such log exists.
        today: Optional override for the current date, primarily for
            testing; defaults to ``date.today()``.

    Returns:
        A :class:`VisitStatusCode` representing the best-effort status.
    """

    if today is None:
        today = date.today()

    # 1) Log-driven lifecycle states take precedence
    if last_log is not None:
        action = last_log.action or ""

        if action == "visit_cancelled":
            return VisitStatusCode.CANCELLED
        if action == "visit_rejected":
            return VisitStatusCode.REJECTED
        if action == "visit_approved":
            return VisitStatusCode.APPROVED
        if action in {"visit_executed_deviation", "visit_executed_with_deviation"}:
            return VisitStatusCode.EXECUTED_WITH_DEVIATION
        if action == "visit_executed":
            return VisitStatusCode.EXECUTED
        if action == "visit_not_executed":
            return VisitStatusCode.NOT_EXECUTED
        if action == "visit_status_cleared":
            pass
        else:
            logger.warning(
                "Unknown visit status action encountered in ActivityLog: %s", action
            )

    # 2) Fallback planning-based states
    from_date = getattr(visit, "from_date", None)
    to_date = getattr(visit, "to_date", None)
    researchers = getattr(visit, "researchers", None) or []
    has_researchers = bool(researchers)
    planned_week = getattr(visit, "planned_week", None)

    # No concrete window yet – considered just created
    if from_date is None or to_date is None:
        return VisitStatusCode.CREATED

    # No researchers assigned and window is in the past
    if to_date < today:
        return VisitStatusCode.OVERDUE

    # Planned week + researchers: PLANNED if the window is current/future,
    # MISSED if the window is already in the past.
    planned_or_week = planned_week is not None or getattr(visit, "planned_date", None) is not None
    if has_researchers and planned_or_week:
        current_week = today.isocalendar()[1]
        
        # If we have a specific planned_date, verify against that
        p_date = getattr(visit, "planned_date", None)
        if p_date is not None:
             if p_date < today:
                 return VisitStatusCode.MISSED
             return VisitStatusCode.PLANNED

        # Fallback to week-based check if only week is present
        if planned_week is not None and planned_week < current_week:
            return VisitStatusCode.MISSED
        return VisitStatusCode.PLANNED

    # Has a date window in the present/future but not yet planned
    return VisitStatusCode.OPEN


async def resolve_visit_status(
    db: AsyncSession,
    visit: Visit,
    *,
    today: date | None = None,
) -> VisitStatusCode:
    """Resolve the status for an in-memory visit using ActivityLog data.

    Args:
        db: Async SQLAlchemy session.
        visit: Visit ORM instance with an ``id`` and relationships
            already loaded (especially ``researchers``) to avoid runtime
            lazy-loading.

    Returns:
        The derived :class:`VisitStatusCode`.
    """

    if visit.id is None:
        # Should not happen for persisted visits; treat as created.
        return VisitStatusCode.CREATED

    last_log = await _latest_status_log_for_visit(db, visit.id)
    return derive_visit_status(visit, last_log, today=today)


async def resolve_visit_status_by_id(
    db: AsyncSession,
    visit_id: int,
    *,
    today: date | None = None,
) -> VisitStatusCode | None:
    """Load a visit by id and return its derived status.

    This helper takes care to eager-load researchers to avoid async
    lazy-loading issues (MissingGreenlet) when computing the fallback
    planning-based status.

    Args:
        db: Async SQLAlchemy session.
        visit_id: Primary key of the visit to inspect.

    Returns:
        The derived :class:`VisitStatusCode`, or ``None`` if the visit
        does not exist.
    """

    stmt: Select[tuple[Visit]] = (
        select(Visit)
        .where(Visit.id == visit_id)
        .options(selectinload(Visit.researchers))
    )
    visit = (await db.execute(stmt)).scalars().first()
    if visit is None:
        return None

    last_log = await _latest_status_log_for_visit(db, visit_id)
    return derive_visit_status(visit, last_log, today=today)


async def resolve_visit_statuses(
    db: AsyncSession,
    visits: list[Visit],
    *,
    today: date | None = None,
) -> dict[int, VisitStatusCode]:
    """Resolve lifecycle statuses for multiple visits efficiently.

    Args:
        db: Async SQLAlchemy session.
        visits: Visit ORM instances with ids and relationships loaded.
        today: Optional override for the current date.

    Returns:
        Mapping of visit id to derived status code.
    """

    visit_ids = [v.id for v in visits if v.id is not None]
    if not visit_ids:
        return {}

    latest_log_subq = (
        select(
            ActivityLog.target_id.label("visit_id"),
            func.max(ActivityLog.created_at).label("latest_at"),
        )
        .where(
            ActivityLog.target_type == "visit",
            ActivityLog.target_id.in_(visit_ids),
            ActivityLog.action.in_(_STATUS_ACTIONS),
        )
        .group_by(ActivityLog.target_id)
        .subquery()
    )

    stmt: Select[tuple[ActivityLog]] = (
        select(ActivityLog)
        .join(
            latest_log_subq,
            (ActivityLog.target_id == latest_log_subq.c.visit_id)
            & (ActivityLog.created_at == latest_log_subq.c.latest_at),
        )
        .where(ActivityLog.target_type == "visit")
    )

    logs = (await db.execute(stmt)).scalars().all()
    log_map = {log.target_id: log for log in logs if log.target_id is not None}

    status_map: dict[int, VisitStatusCode] = {}
    for visit in visits:
        if visit.id is None:
            continue
        status_map[visit.id] = derive_visit_status(
            visit, log_map.get(visit.id), today=today
        )

    return status_map
