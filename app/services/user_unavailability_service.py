from __future__ import annotations

from typing import Sequence
from datetime import date

from sqlalchemy import select, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_unavailability import UserUnavailability
from app.schemas.user_unavailability import UserUnavailabilityCreate, UserUnavailabilityUpdate


async def list_unavailabilities(
    db: AsyncSession, *, user_id: int
) -> Sequence[UserUnavailability]:
    """List all unavailabilities for a user, ordered by start date."""
    stmt = (
        select(UserUnavailability)
        .where(UserUnavailability.user_id == user_id)
        .order_by(UserUnavailability.start_date)
    )
    return (await db.execute(stmt)).scalars().all()


async def get_unavailability(
    db: AsyncSession, *, unavailability_id: int
) -> UserUnavailability | None:
    return await db.get(UserUnavailability, unavailability_id)


async def create_unavailability(
    db: AsyncSession, *, user_id: int, payload: UserUnavailabilityCreate
) -> UserUnavailability:
    """Create a new unavailability. Raises ValueError on overlap."""
    await _check_overlap(
        db, user_id=user_id, start=payload.start_date, end=payload.end_date
    )

    unavailability = UserUnavailability(
        user_id=user_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        morning=payload.morning,
        daytime=payload.daytime,
        nighttime=payload.nighttime,
    )
    db.add(unavailability)
    await db.commit()
    await db.refresh(unavailability)
    return unavailability


async def update_unavailability(
    db: AsyncSession, *, unavailability_id: int, payload: UserUnavailabilityUpdate
) -> UserUnavailability | None:
    """Update an unavailability. Raises ValueError on overlap."""
    unavailability = await get_unavailability(db, unavailability_id=unavailability_id)
    if not unavailability:
        return None

    # Determine effective new range
    new_start = payload.start_date if payload.start_date is not None else unavailability.start_date
    new_end = payload.end_date if payload.end_date is not None else unavailability.end_date

    if new_start != unavailability.start_date or new_end != unavailability.end_date:
        if new_end < new_start:
             raise ValueError("End date must be after start date")

        await _check_overlap(
            db,
            user_id=unavailability.user_id,
            start=new_start,
            end=new_end,
            exclude_id=unavailability_id,
        )
        unavailability.start_date = new_start
        unavailability.end_date = new_end

    if payload.morning is not None:
        unavailability.morning = payload.morning
    if payload.daytime is not None:
        unavailability.daytime = payload.daytime
    if payload.nighttime is not None:
        unavailability.nighttime = payload.nighttime

    await db.commit()
    await db.refresh(unavailability)
    return unavailability


async def delete_unavailability(db: AsyncSession, *, unavailability_id: int) -> bool:
    """Delete an unavailability."""
    stmt = delete(UserUnavailability).where(UserUnavailability.id == unavailability_id)
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount > 0


async def _check_overlap(
    db: AsyncSession,
    *,
    user_id: int,
    start: date,
    end: date,
    exclude_id: int | None = None,
) -> None:
    """Check if the given range overlaps with any existing unavailability for this user."""
    # Overlap logic: (StartA <= EndB) and (EndA >= StartB)
    stmt = select(UserUnavailability).where(
        and_(
            UserUnavailability.user_id == user_id,
            UserUnavailability.start_date <= end,
            UserUnavailability.end_date >= start,
        )
    )
    if exclude_id is not None:
        stmt = stmt.where(UserUnavailability.id != exclude_id)

    existing = (await db.execute(stmt)).scalars().first()
    if existing:
        raise ValueError(
            f"Unavailability overlaps with existing period ({existing.start_date} - {existing.end_date})"
        )
