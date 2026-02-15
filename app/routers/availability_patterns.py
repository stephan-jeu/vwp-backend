from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db

from app.models.user import User
from app.schemas.availability_pattern import (
    AvailabilityPatternCreate,
    AvailabilityPatternUpdate,
    AvailabilityPatternOut,
)
from app.services import availability_pattern_service as service
from app.services.security import require_admin

router = APIRouter()


@router.get("/users/{user_id}/patterns", response_model=list[AvailabilityPatternOut])
async def list_user_patterns(
    user_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    """List availability patterns for a specific user (Admin only)."""
    return await service.list_patterns(db, user_id=user_id)


@router.post(
    "/users/{user_id}/patterns",
    response_model=AvailabilityPatternOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_user_pattern(
    user_id: int,
    payload: AvailabilityPatternCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    """Create a new availability pattern for a user (Admin only)."""
    try:
        return await service.create_pattern(db, user_id=user_id, payload=payload)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )


@router.patch("/patterns/{pattern_id}", response_model=AvailabilityPatternOut)
async def update_pattern(
    pattern_id: int,
    payload: AvailabilityPatternUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    """Update an availability pattern (Admin only)."""
    try:
        updated = await service.update_pattern(db, pattern_id=pattern_id, payload=payload)
        if not updated:
            raise HTTPException(status_code=404, detail="Pattern not found")
        return updated
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )


@router.delete("/patterns/{pattern_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pattern(
    pattern_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    """Delete an availability pattern (Admin only)."""
    success = await service.delete_pattern(db, pattern_id=pattern_id)
    if not success:
        raise HTTPException(status_code=404, detail="Pattern not found")
