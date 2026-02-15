from __future__ import annotations

from typing import Sequence

from sqlalchemy import Select, and_, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.availability import AvailabilityWeek
from app.models.user import User
from app.models.visit import Visit, visit_researchers
from app.schemas.availability import (
    AvailabilityCellUpdate,
    AvailabilityCompact,
    AvailabilityListResponse,
    AvailabilityWeekOut,
    UserAvailability,
)


async def list_by_week_range(
    db: AsyncSession, *, week_start: int, week_end: int
) -> AvailabilityListResponse:
    """List availability for all users for a range of ISO weeks.

    Args:
        db: Async SQLAlchemy session.
        week_start: Start week (inclusive).
        week_end: End week (inclusive).

    Returns:
        AvailabilityListResponse with one entry per user including compact
        week records for each week in the requested range. Missing rows are
        returned with zeros.
    """
    # Load all users; admin status included per requirements
    users_stmt: Select[tuple[User]] = select(User).order_by(User.full_name)
    users: Sequence[User] = (await db.execute(users_stmt)).scalars().all()

    
    # Check feature flag
    from core.settings import get_settings
    settings = get_settings()

    if settings.feature_strict_availability:
        return await _list_by_week_range_strict(db, week_start=week_start, week_end=week_end, users=users)

    # Load all availability rows in the requested scope
    av_stmt: Select[tuple[AvailabilityWeek]] = select(AvailabilityWeek).where(
        and_(
            AvailabilityWeek.week >= week_start,
            AvailabilityWeek.week <= week_end,
        )
    )
    av_rows: Sequence[AvailabilityWeek] = (await db.execute(av_stmt)).scalars().all()

    # Index availability rows by (user_id, week)
    by_key: dict[tuple[int, int], AvailabilityWeek] = {
        (r.user_id, r.week): r for r in av_rows
    }

    # Load assigned visit counts per (user_id, week, part_of_day).
    # A visit contributes to the total when it has a planned_week within the
    # requested range and at least one linked researcher record. Flex capacity
    # does not get a separate total.
    assignments_stmt = (
        select(
            visit_researchers.c.user_id,
            Visit.planned_week,
            Visit.part_of_day,
            func.count().label("cnt"),
        )
        .join(visit_researchers, visit_researchers.c.visit_id == Visit.id)
        .where(
            and_(
                Visit.planned_week.is_not(None),
                Visit.planned_week >= week_start,
                Visit.planned_week <= week_end,
                Visit.part_of_day.is_not(None),
            )
        )
        .group_by(visit_researchers.c.user_id, Visit.planned_week, Visit.part_of_day)
    )

    assignments_result = await db.execute(assignments_stmt)
    assignments_rows = assignments_result.all()

    # Map (user_id, week) -> {"morning": int, "daytime": int, "evening": int}
    assigned_by_key: dict[tuple[int, int], dict[str, int]] = {}
    for user_id, week, part_of_day, cnt in assignments_rows:
        if user_id is None or week is None or part_of_day is None:
            continue
        key = (int(user_id), int(week))
        bucket = assigned_by_key.setdefault(
            key,
            {"morning": 0, "daytime": 0, "evening": 0},
        )

        label = str(part_of_day).strip()
        count_int = int(cnt or 0)
        if label == "Ochtend":
            bucket["morning"] += count_int
        elif label == "Dag":
            bucket["daytime"] += count_int
        elif label == "Avond":
            bucket["evening"] += count_int
        # Other parts (including flex) are ignored for availability totals.

    users_payload: list[UserAvailability] = []
    for u in users:
        weeks: list[AvailabilityCompact] = []
        for w in range(week_start, week_end + 1):
            row = by_key.get((u.id, w))
            assigned = assigned_by_key.get((u.id, w), {})
            if row is None:
                weeks.append(
                    AvailabilityCompact(
                        week=w,
                        morning_days=0,
                        daytime_days=0,
                        nighttime_days=0,
                        flex_days=0,
                        assigned_morning=int(assigned.get("morning", 0)),
                        assigned_daytime=int(assigned.get("daytime", 0)),
                        assigned_evening=int(assigned.get("evening", 0)),
                    )
                )
            else:
                weeks.append(
                    AvailabilityCompact(
                        week=w,
                        morning_days=row.morning_days,
                        daytime_days=row.daytime_days,
                        nighttime_days=row.nighttime_days,
                        flex_days=row.flex_days,
                        assigned_morning=int(assigned.get("morning", 0)),
                        assigned_daytime=int(assigned.get("daytime", 0)),
                        assigned_evening=int(assigned.get("evening", 0)),
                    )
                )
        users_payload.append(
            UserAvailability(id=u.id, name=u.full_name or u.email, availability=weeks)
        )

    return AvailabilityListResponse(users=list(users_payload))


async def _list_by_week_range_strict(
    db: AsyncSession, *, week_start: int, week_end: int, users: Sequence[User]
) -> AvailabilityListResponse:
    from app.models.availability_pattern import AvailabilityPattern
    from datetime import date, timedelta
    
    # 1. Fetch all patterns for all users that overlap with the date range of these weeks
    # For simplicity, we fetch all patterns for now or do a broad query.
    # To do it right: calculate start_date of week_start and end_date of week_end.
    
    # Rough approximation of current year for ISO weeks. 
    # NOTE: This implies we only support current year planning for now or need year input.
    # The existing API `list_by_week_range` takes `week_start` (int) without year. 
    # The frontend usually assumes "current/relevant" year. 
    # We will assume the year of "today" for the week calculation to find the date range.
    today = date.today()
    year = today.year
    
    # Calculate date range for the weeks
    # ISO week 1 starts on the Monday of the week containing Jan 4th.
    def get_start_of_iso_week(y, w):
        jan4 = date(y, 1, 4)
        start_of_year_week = jan4 - timedelta(days=jan4.isoweekday() - 1)
        return start_of_year_week + timedelta(weeks=w - 1)

    start_date = get_start_of_iso_week(year, week_start)
    # end date is end of week_end
    end_date_start_week = get_start_of_iso_week(year, week_end)
    end_date = end_date_start_week + timedelta(days=6)

    # Fetch patterns
    patterns_stmt = select(AvailabilityPattern).where(
        and_(
            AvailabilityPattern.start_date <= end_date,
            AvailabilityPattern.end_date >= start_date,
        )
    )
    patterns = (await db.execute(patterns_stmt)).scalars().all()
    
    # Organise patterns by user
    patterns_by_user: dict[int, list[AvailabilityPattern]] = {}
    for p in patterns:
        patterns_by_user.setdefault(p.user_id, []).append(p)

    # Also need assignments (same logic as normal flow)
    # Load assigned visit counts per (user_id, week, part_of_day).
    assignments_stmt = (
        select(
            visit_researchers.c.user_id,
            Visit.planned_week,
            Visit.part_of_day,
            func.count().label("cnt"),
        )
        .join(visit_researchers, visit_researchers.c.visit_id == Visit.id)
        .where(
            and_(
                Visit.planned_week.is_not(None),
                Visit.planned_week >= week_start,
                Visit.planned_week <= week_end,
                Visit.part_of_day.is_not(None),
            )
        )
        .group_by(visit_researchers.c.user_id, Visit.planned_week, Visit.part_of_day)
    )
    assignments_result = await db.execute(assignments_stmt)
    assigned_by_key: dict[tuple[int, int], dict[str, int]] = {}
    for user_id, week, part_of_day, cnt in assignments_result.all():
         if user_id is None or week is None or part_of_day is None:
            continue
         key = (int(user_id), int(week))
         bucket = assigned_by_key.setdefault(key, {"morning": 0, "daytime": 0, "evening": 0})
         label = str(part_of_day).strip()
         count_int = int(cnt or 0)
         if label == "Ochtend": bucket["morning"] += count_int
         elif label == "Dag": bucket["daytime"] += count_int
         elif label == "Avond": bucket["evening"] += count_int

    users_payload: list[UserAvailability] = []
    
    for u in users:
        user_patterns = patterns_by_user.get(u.id, [])
        weeks_data: list[AvailabilityCompact] = []
        
        for w in range(week_start, week_end + 1):
            w_start = get_start_of_iso_week(year, w)
            
            # Calculate capacity for this week based on patterns
            # A simplistic approach: Iterate days Mon-Fri (or Mon-Sun)
            # Find applicable pattern for each day.
            # Sum up slots.
            
            morning_cap = 0
            daytime_cap = 0
            nighttime_cap = 0
            
            for i in range(5): # Mon(0) to Fri(4) - assuming weekends irrelevant for now or handled? 
                # Strict availability usually implies work week. 
                # check if pattern covers this day
                day_date = w_start + timedelta(days=i)
                
                # Find active pattern
                active_pattern = next(
                    (p for p in user_patterns if p.start_date <= day_date <= p.end_date), 
                    None
                )
                
                if active_pattern:
                    # Get schedule for this day
                    # day_date.weekday() -> 0=Mon, ...
                    day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
                    day_name = day_names[day_date.weekday()]
                    
                    slots = active_pattern.schedule.get(day_name, [])
                    if "morning" in slots: morning_cap += 1
                    if "daytime" in slots: daytime_cap += 1
                    if "nighttime" in slots: nighttime_cap += 1
            
            assigned = assigned_by_key.get((u.id, w), {})
            
            weeks_data.append(
                AvailabilityCompact(
                    week=w,
                    morning_days=morning_cap,
                    daytime_days=daytime_cap,
                    nighttime_days=nighttime_cap,
                    flex_days=0, # No flex in strict mode
                    assigned_morning=int(assigned.get("morning", 0)),
                    assigned_daytime=int(assigned.get("daytime", 0)),
                    assigned_evening=int(assigned.get("evening", 0)),
                )
            )

        users_payload.append(
            UserAvailability(id=u.id, name=u.full_name or u.email, availability=weeks_data)
        )

    return AvailabilityListResponse(users=list(users_payload))


async def upsert_cell(
    db: AsyncSession,
    *,
    user_id: int,
    week: int,
    payload: AvailabilityCellUpdate,
) -> AvailabilityWeekOut:
    """Upsert a single availability slot value for a given (user, year, week).

    Args:
        db: Async SQLAlchemy session.
        user_id: Target user id.
        week: ISO week.
        payload: Slot and new value (0-7).

    Returns:
        The normalized AvailabilityWeek row after applying the change.
    """
    # Try to get existing row
    row = (
        (
            await db.execute(
                select(AvailabilityWeek).where(
                    and_(
                        AvailabilityWeek.user_id == user_id,
                        AvailabilityWeek.week == week,
                    )
                )
            )
        )
        .scalars()
        .first()
    )

    if row is None:
        row = AvailabilityWeek(
            user_id=user_id,
            week=week,
            morning_days=0,
            daytime_days=0,
            nighttime_days=0,
            flex_days=0,
        )
        db.add(row)

    # Apply update to the requested slot
    if payload.slot == "morning":
        row.morning_days = payload.value
    elif payload.slot == "daytime":
        row.daytime_days = payload.value
    elif payload.slot == "nighttime":
        row.nighttime_days = payload.value
    else:
        row.flex_days = payload.value

    await db.commit()
    await db.refresh(row)

    return AvailabilityWeekOut.model_validate(row, from_attributes=True)


async def get_user_availability(
    db: AsyncSession, *, user_id: int, week_start: int, week_end: int
) -> list[AvailabilityWeek]:
    """Get availability for a specific user for a week range.

    Args:
        db: Async SQLAlchemy session.
        user_id: User ID.
        week_start: Start week (inclusive).
        week_end: End week (inclusive).

    Returns:
        List of AvailabilityWeek rows.
    """
    stmt = (
        select(AvailabilityWeek)
        .where(
            and_(
                AvailabilityWeek.user_id == user_id,
                AvailabilityWeek.week >= week_start,
                AvailabilityWeek.week <= week_end,
            )
        )
        .order_by(AvailabilityWeek.week)
    )
    return (await db.execute(stmt)).scalars().all()
