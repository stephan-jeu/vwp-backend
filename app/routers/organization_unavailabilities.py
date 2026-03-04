from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db
from app.models.user import User
from app.schemas.organization_unavailability import (
    OrganizationUnavailabilityCreate,
    OrganizationUnavailabilityUpdate,
    OrganizationUnavailabilityOut,
)
from app.services import organization_unavailability_service as service
from app.services.security import require_admin

router = APIRouter()


@router.get(
    "/organization-unavailabilities",
    response_model=list[OrganizationUnavailabilityOut],
)
async def list_organization_unavailabilities(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_admin)],
    year: int = Query(default=None, description="Filter by year (defaults to current year)"),
):
    """List organization unavailabilities for a given year. (Admins only)"""
    if year is None:
        from datetime import date
        year = date.today().year
    return await service.list_unavailabilities(db, year=year)


@router.post(
    "/organization-unavailabilities",
    response_model=OrganizationUnavailabilityOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_organization_unavailability(
    payload: OrganizationUnavailabilityCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_admin)],
):
    """Create a new organization unavailability. (Admins only)"""
    try:
        return await service.create_unavailability(db, payload=payload)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.patch(
    "/organization-unavailabilities/{unavailability_id}",
    response_model=OrganizationUnavailabilityOut,
)
async def update_organization_unavailability(
    unavailability_id: int,
    payload: OrganizationUnavailabilityUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_admin)],
):
    """Update an organization unavailability. (Admins only)"""
    existing = await service.get_unavailability(db, unavailability_id=unavailability_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Unavailability not found")

    try:
        updated = await service.update_unavailability(
            db, unavailability_id=unavailability_id, payload=payload
        )
        return updated
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete(
    "/organization-unavailabilities/{unavailability_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_organization_unavailability(
    unavailability_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_admin)],
):
    """Delete an organization unavailability. (Admins only)"""
    existing = await service.get_unavailability(db, unavailability_id=unavailability_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Unavailability not found")

    success = await service.delete_unavailability(db, unavailability_id=unavailability_id)
    if not success:
        raise HTTPException(status_code=404, detail="Unavailability not found")


@router.post(
    "/organization-unavailabilities/seed/{year}",
    response_model=list[OrganizationUnavailabilityOut],
)
async def seed_organization_unavailabilities(
    year: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_admin)],
):
    """Reset all entries and seed Dutch public holidays for the given year. (Admins only)"""
    return await service.reset_and_seed_year(db, year=year)
