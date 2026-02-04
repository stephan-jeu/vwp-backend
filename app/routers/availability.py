from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.availability import AvailabilityWeekOut
from app.services.availability_service import get_user_availability
from app.services.security import get_current_user
from db.session import get_db

router = APIRouter()

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.get("/me", response_model=list[AvailabilityWeekOut])
async def get_my_availability(
    current_user: UserDep,
    db: DbDep,
    week_start: int | None = Query(None, ge=1, le=53),
    week_end: int | None = Query(None, ge=1, le=53),
) -> list[AvailabilityWeekOut]:
    """Get weekly availability for the current user.

    If start/end weeks are not provided, returns a default range (e.g., current week onwards).
    However, for now, we'll require at least a reasonable default if not specified by frontend,
    or just return empty if ranges are weird.
    Actually, let's look at `admin_availability.py` logic. It demands week_start/end.
    Here we can make them optional and default to "now" + 10 weeks if needed,
    but it's better to let frontend drive it.
    If param is missing, we can default to 1-53 or similar logic if appropriate,
    but typically frontend knows what it wants.
    Let's make them optional but default to full year if missing? Or maybe just require them?
    The prompt said "Modify my-visits page... ordered by week number".
    Let's default to a wide range if not specified to be safe, or just current week.
    Let's default week_start to 1 and week_end to 53 if not provided.
    """
    start = week_start if week_start is not None else 1
    end = week_end if week_end is not None else 53
    
    # Simple validation swap if needed
    if start > end:
        start, end = end, start

    return await get_user_availability(
        db, user_id=current_user.id, week_start=start, week_end=end
    )
