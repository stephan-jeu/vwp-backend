from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.deps import AdminDep, DbDep
from app.schemas.availability import (
    AvailabilityCellUpdate,
    AvailabilityListResponse,
    AvailabilityWeekOut,
)
from app.services.availability_service import list_by_week_range, upsert_cell

router = APIRouter()


@router.get("/availability", response_model=AvailabilityListResponse)
async def get_availability(
    _: AdminDep,
    db: DbDep,
    week_start: int = Query(..., ge=1, le=53),
    week_end: int = Query(..., ge=1, le=53),
) -> AvailabilityListResponse:
    """List availability for all users for a given week range (admin only)."""
    return await list_by_week_range(db, week_start=week_start, week_end=week_end)


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
