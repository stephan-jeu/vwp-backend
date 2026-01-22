from __future__ import annotations
import logging
from datetime import date, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from app.models.visit import Visit
from app.models.protocol_visit_window import ProtocolVisitWindow
from app.models.visit import visit_protocol_visit_windows

_logger = logging.getLogger("uvicorn.error")


async def sanitize_future_planning(
    db: AsyncSession, week_monday: date, newly_planned_visit_ids: list[int]
) -> list[int]:
    """
    Check for scheduling conflicts in FUTURE weeks caused by the newly scheduled visits
    in the current week. If a future visit (within 3 weeks) belongs to the same
    protocol as a newly scheduled visit, it violates the frequency constraint
    and must be unscheduled (sanitized).

    Returns a list of visit IDs that were sanitized (unplanned).
    """
    if not newly_planned_visit_ids:
        return []

    current_week = week_monday.isocalendar().week

    # 1. Get protocols of newly planned visits
    stmt_new = (
        select(Visit)
        .where(Visit.id.in_(newly_planned_visit_ids))
        .options(selectinload(Visit.protocol_visit_windows))
    )
    new_visits = (await db.execute(stmt_new)).scalars().unique().all()

    new_protocols = set()
    for v in new_visits:
        for pvw in v.protocol_visit_windows or []:
            new_protocols.add(pvw.protocol_id)

    if not new_protocols:
        return []

    # 2. Look Ahead: Find "Locked" visits in the future (up to 8 weeks)
    # that belong to these protocols.

    # We query up to 8 weeks ahead to cover most frequency requirements.

    future_start_date = week_monday + timedelta(days=7)  # Next Monday
    future_end_date = week_monday + timedelta(weeks=9)  # 9 weeks buffer

    # We need to fetch Protocol info (min period) for the FUTURE visits too,
    # or rely on the fact we already know the 'new_protocols' (but we need their period).
    # Easier to just fetch the future visits with their Protocol info.

    from app.models.protocol import Protocol

    stmt_future = (
        select(
            Visit,
            Protocol.id.label("protocol_id"),
            Protocol.min_period_between_visits_value,
            Protocol.min_period_between_visits_unit,
        )
        .join(
            visit_protocol_visit_windows,
            visit_protocol_visit_windows.c.visit_id == Visit.id,
        )
        .join(
            ProtocolVisitWindow,
            ProtocolVisitWindow.id
            == visit_protocol_visit_windows.c.protocol_visit_window_id,
        )
        .join(Protocol, Protocol.id == ProtocolVisitWindow.protocol_id)
        .where(
            and_(
                Visit.planned_week > current_week,
                # Optimization: Limit search horizon
                Visit.from_date >= future_start_date,
                Visit.from_date <= future_end_date,
                Visit.researchers.any(),  # Only locked visits
                Protocol.id.in_(new_protocols),  # Only check relevant protocols
            )
        )
        .options(selectinload(Visit.researchers))
    )

    # Execute query
    results = (await db.execute(stmt_future)).unique().all()

    sanitized_ids = set()

    for visit_future, prot_id, min_val, min_unit in results:
        if visit_future.id in sanitized_ids:
            continue

        if not min_val:
            continue

        # Check gap between "newly planned visit in current week" and this "future visit".
        # Current week "End Date" roughly week_monday + 4 (Friday).
        # OR just use 'future_visit.from_date' - 'current_week_friday'

        current_week_end = week_monday + timedelta(days=4)

        # Calculate required gap
        required_gap_days = 0
        if min_unit == "weeks":
            required_gap_days = min_val * 7
        elif min_unit == "months":
            required_gap_days = min_val * 30
        else:
            required_gap_days = min_val

        # Actual Gap = Future Start - Current End
        if not visit_future.from_date:
            continue  # Can't calculate exact gap

        days_diff = (visit_future.from_date - current_week_end).days

        if days_diff < required_gap_days:
            # Violation!
            if visit_future.researchers:
                visit_future.researchers.clear()
            visit_future.planned_week = None
            sanitized_ids.add(visit_future.id)

            _logger.warning(
                "Sanitizing future visit %s (Week %s, Protocol %s) due to frequency conflict (< %s %s) with new plan in Week %s",
                visit_future.id,
                visit_future.planned_week,
                prot_id,
                min_val,
                min_unit,
                current_week,
            )

    # We return list of IDs
    result_ids = list(sanitized_ids)

    await db.commit()
    return result_ids
