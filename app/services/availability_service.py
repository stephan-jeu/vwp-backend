from __future__ import annotations

from typing import Sequence

from sqlalchemy import Select, and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.availability import AvailabilityWeek
from app.models.user import User
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

    # Load all availability rows in the requested scope
    av_stmt: Select[tuple[AvailabilityWeek]] = select(AvailabilityWeek).where(
        and_(
            AvailabilityWeek.week >= week_start,
            AvailabilityWeek.week <= week_end,
        )
    )
    av_rows: Sequence[AvailabilityWeek] = (await db.execute(av_stmt)).scalars().all()

    # Index by (user_id, week)
    by_key: dict[tuple[int, int], AvailabilityWeek] = {
        (r.user_id, r.week): r for r in av_rows
    }

    users_payload: list[UserAvailability] = []
    for u in users:
        weeks: list[AvailabilityCompact] = []
        for w in range(week_start, week_end + 1):
            row = by_key.get((u.id, w))
            if row is None:
                weeks.append(
                    AvailabilityCompact(
                        week=w,
                        morning_days=0, 
                        nighttime_days=0, 
                        flex_days=0
                    )
                )
            else:
                weeks.append(
                    AvailabilityCompact(
                        week=w,
                        morning_days=row.morning_days,
                        nighttime_days=row.nighttime_days,
                        flex_days=row.flex_days,
                    )
                )
        users_payload.append(
            UserAvailability(id=u.id, name=u.full_name or u.email, availability=weeks)
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
        await db.execute(
            select(AvailabilityWeek).where(
                and_(
                    AvailabilityWeek.user_id == user_id,
                    AvailabilityWeek.week == week,
                )
            )
        )
    ).scalars().first()

    if row is None:
        row = AvailabilityWeek(
            user_id=user_id,
            week=week,
            morning_days=0,
            nighttime_days=0,
            flex_days=0,
        )
        db.add(row)

    # Apply update to the requested slot
    if payload.slot == "morning":
        row.morning_days = payload.value
    elif payload.slot == "nighttime":
        row.nighttime_days = payload.value
    else:
        row.flex_days = payload.value

    await db.commit()
    await db.refresh(row)

    return AvailabilityWeekOut.model_validate(row, from_attributes=True)
