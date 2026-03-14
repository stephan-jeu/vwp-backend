from __future__ import annotations

from datetime import date
from typing import Sequence

from sqlalchemy import and_, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.utils import select_active
from app.models.organization_unavailability import OrganizationUnavailability
from app.schemas.organization_unavailability import (
    OrganizationUnavailabilityCreate,
    OrganizationUnavailabilityUpdate,
)


async def list_unavailabilities(
    db: AsyncSession, *, year: int
) -> Sequence[OrganizationUnavailability]:
    """List all organization unavailabilities that overlap with the given year."""
    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)
    stmt = (
        select_active(OrganizationUnavailability)
        .where(
            and_(
                OrganizationUnavailability.start_date <= year_end,
                OrganizationUnavailability.end_date >= year_start,
            )
        )
        .order_by(OrganizationUnavailability.start_date)
    )
    return (await db.execute(stmt)).scalars().all()


async def get_unavailability(
    db: AsyncSession, *, unavailability_id: int
) -> OrganizationUnavailability | None:
    return await db.get(OrganizationUnavailability, unavailability_id)


async def create_unavailability(
    db: AsyncSession, *, payload: OrganizationUnavailabilityCreate
) -> OrganizationUnavailability:
    """Create a new organization unavailability. Raises ValueError on overlap."""
    await _check_overlap(db, start=payload.start_date, end=payload.end_date)

    unavailability = OrganizationUnavailability(
        start_date=payload.start_date,
        end_date=payload.end_date,
        morning=payload.morning,
        daytime=payload.daytime,
        nighttime=payload.nighttime,
        description=payload.description,
        is_default=payload.is_default,
    )
    db.add(unavailability)
    await db.commit()
    await db.refresh(unavailability)
    return unavailability


async def update_unavailability(
    db: AsyncSession,
    *,
    unavailability_id: int,
    payload: OrganizationUnavailabilityUpdate,
) -> OrganizationUnavailability | None:
    """Update an organization unavailability. Raises ValueError on overlap."""
    unavailability = await get_unavailability(db, unavailability_id=unavailability_id)
    if not unavailability:
        return None

    new_start = (
        payload.start_date
        if payload.start_date is not None
        else unavailability.start_date
    )
    new_end = (
        payload.end_date if payload.end_date is not None else unavailability.end_date
    )

    if new_start != unavailability.start_date or new_end != unavailability.end_date:
        if new_end < new_start:
            raise ValueError("End date must be after start date")
        await _check_overlap(
            db, start=new_start, end=new_end, exclude_id=unavailability_id
        )
        unavailability.start_date = new_start
        unavailability.end_date = new_end

    if payload.morning is not None:
        unavailability.morning = payload.morning
    if payload.daytime is not None:
        unavailability.daytime = payload.daytime
    if payload.nighttime is not None:
        unavailability.nighttime = payload.nighttime
    if payload.description is not None:
        unavailability.description = payload.description

    await db.commit()
    await db.refresh(unavailability)
    return unavailability


async def delete_unavailability(db: AsyncSession, *, unavailability_id: int) -> bool:
    """Delete an organization unavailability."""
    stmt = delete(OrganizationUnavailability).where(
        OrganizationUnavailability.id == unavailability_id
    )
    result = await db.execute(stmt)
    await db.commit()
    return result.rowcount > 0


async def reset_and_seed_year(
    db: AsyncSession, *, year: int
) -> list[OrganizationUnavailability]:
    """Delete all existing entries and seed Dutch public holidays for the given year.

    Returns the list of seeded entries.
    """
    # Hard-delete all existing organization unavailabilities (all years)
    await db.execute(delete(OrganizationUnavailability))

    holidays = _compute_dutch_holidays(year)
    created = []
    for h in holidays:
        entry = OrganizationUnavailability(
            start_date=h["date"],
            end_date=h["date"],
            morning=True,
            daytime=True,
            nighttime=True,
            description=h["name"],
            is_default=True,
        )
        db.add(entry)
        created.append(entry)

    await db.commit()
    for entry in created:
        await db.refresh(entry)
    return created


def _compute_dutch_holidays(year: int) -> list[dict]:
    """Compute official Dutch public holidays for a given year.

    Returns a list of dicts with keys: 'name' and 'date'.
    """
    from datetime import timedelta

    easter = _easter_sunday(year)

    holidays = [
        {"name": "Nieuwjaarsdag", "date": date(year, 1, 1)},
        {"name": "Goede Vrijdag", "date": easter - timedelta(days=2)},
        {"name": "Eerste Paasdag", "date": easter},
        {"name": "Tweede Paasdag", "date": easter + timedelta(days=1)},
        {"name": "Koningsdag", "date": _koningsdag(year)},
        {"name": "Bevrijdingsdag", "date": date(year, 5, 5)},
        {"name": "Hemelvaartsdag", "date": easter + timedelta(days=39)},
        {"name": "Eerste Pinksterdag", "date": easter + timedelta(days=49)},
        {"name": "Tweede Pinksterdag", "date": easter + timedelta(days=50)},
        {"name": "Eerste Kerstdag", "date": date(year, 12, 25)},
        {"name": "Tweede Kerstdag", "date": date(year, 12, 26)},
    ]
    return holidays


def _easter_sunday(year: int) -> date:
    """Calculate Easter Sunday for a given year using the Anonymous Gregorian algorithm."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month = (h + ell - 7 * m + 114) // 31
    day = ((h + ell - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _koningsdag(year: int) -> date:
    """April 27, moved to April 26 when April 27 falls on a Sunday."""

    d = date(year, 4, 27)
    if d.weekday() == 6:  # Sunday
        return date(year, 4, 26)
    return d


async def _check_overlap(
    db: AsyncSession,
    *,
    start: date,
    end: date,
    exclude_id: int | None = None,
) -> None:
    """Check if the given range overlaps with any existing organization unavailability."""
    stmt = select_active(OrganizationUnavailability).where(
        and_(
            OrganizationUnavailability.start_date <= end,
            OrganizationUnavailability.end_date >= start,
        )
    )
    if exclude_id is not None:
        stmt = stmt.where(OrganizationUnavailability.id != exclude_id)

    existing = (await db.execute(stmt)).scalars().first()
    if existing:
        raise ValueError(
            f"Period overlaps with existing entry ({existing.start_date} – {existing.end_date})"
        )
