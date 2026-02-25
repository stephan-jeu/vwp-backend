from __future__ import annotations

from typing import Sequence
from datetime import date

from sqlalchemy import select, and_, or_, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.availability_pattern import AvailabilityPattern
from app.schemas.availability_pattern import AvailabilityPatternCreate, AvailabilityPatternUpdate


async def list_patterns(
    db: AsyncSession, *, user_id: int
) -> Sequence[AvailabilityPattern]:
    """List all availability patterns for a user, ordered by start date."""
    stmt = (
        select(AvailabilityPattern)
        .where(AvailabilityPattern.user_id == user_id)
        .order_by(AvailabilityPattern.start_date)
    )
    return (await db.execute(stmt)).scalars().all()


async def get_pattern(
    db: AsyncSession, *, pattern_id: int
) -> AvailabilityPattern | None:
    return await db.get(AvailabilityPattern, pattern_id)


async def create_pattern(
    db: AsyncSession, *, user_id: int, payload: AvailabilityPatternCreate
) -> AvailabilityPattern:
    """Create a new pattern. Raises ValueError on overlap."""
    await _check_overlap(
        db, user_id=user_id, start=payload.start_date, end=payload.end_date
    )

    pattern = AvailabilityPattern(
        user_id=user_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        max_mornings_per_week=payload.max_mornings_per_week,
        max_evenings_per_week=payload.max_evenings_per_week,
        schedule=payload.schedule,
    )
    db.add(pattern)
    await db.commit()
    await db.refresh(pattern)
    return pattern


async def update_pattern(
    db: AsyncSession, *, pattern_id: int, payload: AvailabilityPatternUpdate
) -> AvailabilityPattern | None:
    """Update a pattern. Raises ValueError on overlap."""
    pattern = await get_pattern(db, pattern_id=pattern_id)
    if not pattern:
        return None

    # Determine effective new range
    new_start = payload.start_date if payload.start_date is not None else pattern.start_date
    new_end = payload.end_date if payload.end_date is not None else pattern.end_date

    if new_start != pattern.start_date or new_end != pattern.end_date:
        if new_end < new_start:
             raise ValueError("End date must be after start date")

        await _check_overlap(
            db,
            user_id=pattern.user_id,
            start=new_start,
            end=new_end,
            exclude_id=pattern_id,
        )
        pattern.start_date = new_start
        pattern.end_date = new_end

    if payload.max_mornings_per_week is not None:
        pattern.max_mornings_per_week = payload.max_mornings_per_week
    
    if payload.max_evenings_per_week is not None:
        pattern.max_evenings_per_week = payload.max_evenings_per_week
    
    if payload.schedule is not None:
        pattern.schedule = payload.schedule

    await db.commit()
    await db.refresh(pattern)
    return pattern


async def delete_pattern(db: AsyncSession, *, pattern_id: int) -> bool:
    """Delete a pattern."""
    stmt = delete(AvailabilityPattern).where(AvailabilityPattern.id == pattern_id)
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
    """Check if the given range overlaps with any existing pattern for this user."""
    # Overlap logic: (StartA <= EndB) and (EndA >= StartB)
    stmt = select(AvailabilityPattern).where(
        and_(
            AvailabilityPattern.user_id == user_id,
            AvailabilityPattern.start_date <= end,
            AvailabilityPattern.end_date >= start,
        )
    )
    if exclude_id is not None:
        stmt = stmt.where(AvailabilityPattern.id != exclude_id)

    existing = (await db.execute(stmt)).scalars().first()
    if existing:
        raise ValueError(
            f"Pattern overlaps with existing period ({existing.start_date} - {existing.end_date})"
        )
