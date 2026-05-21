from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Path, Query
from sqlalchemy import select

from app.deps import AdminDep, DbDep
from app.models.user import User
from app.models.user_unavailability import UserUnavailability
from app.db.utils import select_active
from app.schemas.availability import (
    AvailabilityCellUpdate,
    AvailabilityListResponse,
    AvailabilityWeekOut,
    UnavailabilityDayInfo,
    UserWeekUnavailability,
    WeekUnavailabilityResponse,
)
from app.services.availability_service import list_by_week_range, upsert_cell
from core.settings import get_settings

router = APIRouter()

_settings = get_settings()


@router.get("/availability", response_model=AvailabilityListResponse)
async def get_availability(
    _: AdminDep,
    db: DbDep,
    week_start: int = Query(..., ge=1, le=53),
    week_end: int = Query(..., ge=1, le=53),
) -> AvailabilityListResponse:
    """List availability for all users for a given week range (admin only)."""
    return await list_by_week_range(db, week_start=week_start, week_end=week_end)


@router.get("/unavailabilities/week", response_model=WeekUnavailabilityResponse)
async def get_week_unavailabilities(
    _: AdminDep,
    db: DbDep,
    week: int = Query(..., ge=1, le=53),
    year: int | None = Query(None),
) -> WeekUnavailabilityResponse:
    """Return per-day unavailability for all researchers in the given ISO week.

    Only meaningful when FEATURE_STRICT_AVAILABILITY is enabled.
    """
    effective_year = year if year else date.today().year
    monday = date.fromisocalendar(effective_year, week, 1)
    friday = monday + timedelta(days=4)

    # Load all active unavailabilities that overlap [monday, friday]
    stmt = (
        select_active(UserUnavailability)
        .where(
            UserUnavailability.start_date <= friday,
            UserUnavailability.end_date >= monday,
        )
        .join(User, User.id == UserUnavailability.user_id)
        .add_columns(User.full_name)
    )
    rows = (await db.execute(stmt)).all()

    # Group by user
    user_map: dict[int, UserWeekUnavailability] = {}
    for unavailability, full_name in rows:
        uid = unavailability.user_id
        if uid not in user_map:
            user_map[uid] = UserWeekUnavailability(
                user_id=uid,
                user_name=full_name or f"Gebruiker #{uid}",
                dates={},
            )
        entry = user_map[uid]

        # Expand the unavailability range to individual dates within [monday, friday]
        span_start = max(unavailability.start_date, monday)
        span_end = min(unavailability.end_date, friday)
        current = span_start
        while current <= span_end:
            iso = current.isoformat()
            if iso not in entry.dates:
                entry.dates[iso] = UnavailabilityDayInfo(
                    morning=unavailability.morning,
                    daytime=unavailability.daytime,
                    nighttime=unavailability.nighttime,
                )
            else:
                # Merge: mark as unavailable if any record covers this part
                existing = entry.dates[iso]
                entry.dates[iso] = UnavailabilityDayInfo(
                    morning=existing.morning or unavailability.morning,
                    daytime=existing.daytime or unavailability.daytime,
                    nighttime=existing.nighttime or unavailability.nighttime,
                )
            current += timedelta(days=1)

    return WeekUnavailabilityResponse(week=week, users=list(user_map.values()))


@router.patch("/availability/{user_id}/{week}", response_model=AvailabilityWeekOut)
async def patch_availability_cell(
    _: AdminDep,
    db: DbDep,
    user_id: int = Path(..., ge=1),
    week: int = Path(..., ge=1, le=53),
    payload: AvailabilityCellUpdate | None = None,
) -> AvailabilityWeekOut:
    """Update a single availability cell (admin only). Upserts the week row."""
    assert payload is not None
    return await upsert_cell(db, user_id=user_id, week=week, payload=payload)
