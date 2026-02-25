from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db

from app.models.user import User
from app.schemas.user_unavailability import (
    UserUnavailabilityCreate,
    UserUnavailabilityUpdate,
    UserUnavailabilityOut,
)
from app.services import user_unavailability_service as service
from app.services.security import require_admin

router = APIRouter()


@router.get("/users/{user_id}/unavailabilities", response_model=list[UserUnavailabilityOut])
async def list_user_unavailabilities(
    user_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    """List unavailabilities for a specific user. (Admins only)"""
    return await service.list_unavailabilities(db, user_id=user_id)


@router.post(
    "/users/{user_id}/unavailabilities",
    response_model=UserUnavailabilityOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_user_unavailability(
    user_id: int,
    payload: UserUnavailabilityCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    """Create a new unavailability for a user. (Admins only)"""
    try:
        return await service.create_unavailability(db, user_id=user_id, payload=payload)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )


@router.patch("/unavailabilities/{unavailability_id}", response_model=UserUnavailabilityOut)
async def update_unavailability(
    unavailability_id: int,
    payload: UserUnavailabilityUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    """Update an unavailability. (Admins only)"""
    existing = await service.get_unavailability(db, unavailability_id=unavailability_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Unavailability not found")

    try:
        updated = await service.update_unavailability(db, unavailability_id=unavailability_id, payload=payload)
        return updated
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )


@router.delete("/unavailabilities/{unavailability_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_unavailability(
    unavailability_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    """Delete an unavailability. (Admins only)"""
    existing = await service.get_unavailability(db, unavailability_id=unavailability_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Unavailability not found")

    success = await service.delete_unavailability(db, unavailability_id=unavailability_id)
    if not success:
        raise HTTPException(status_code=404, detail="Unavailability not found")
