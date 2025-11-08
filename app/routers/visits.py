from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy import select, delete, insert
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.visit import Visit
from app.models.function import Function
from app.models.species import Species
from app.models.visit import visit_functions, visit_species
from app.schemas.visit import VisitRead, VisitUpdate
from db.session import get_db
from app.services.security import require_admin

router = APIRouter()


DbDep = Annotated[AsyncSession, Depends(get_db)]
AdminDep = Annotated[object, Depends(require_admin)]


@router.get("")
async def list_visits() -> list[dict[str, str]]:
    """List visits placeholder endpoint."""
    return []


@router.put("/{visit_id}", response_model=VisitRead)
async def update_visit(
    _: AdminDep, db: DbDep, visit_id: int, payload: VisitUpdate
) -> Visit:
    """Update a visit with provided fields.

    For now we accept the VisitRead payload to keep implementation minimal; in a
    follow-up we can tighten this to a dedicated VisitUpdate schema.
    """

    visit = await db.get(Visit, visit_id)
    if visit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    # Map simple scalar fields if provided
    for field in (
        "required_researchers",
        "visit_nr",
        "from_date",
        "to_date",
        "duration",
        "min_temperature_celsius",
        "max_wind_force_bft",
        "max_precipitation",
        "planned_week",
        "part_of_day",
        "start_time_text",
        "expertise_level",
        "wbc",
        "fiets",
        "hup",
        "dvp",
        "sleutel",
        "remarks_planning",
        "remarks_field",
        "priority",
        "preferred_researcher_id",
        "advertized",
        "quote",
    ):
        value = getattr(payload, field)
        if value is not None:
            setattr(visit, field, value)

    # Handle many-to-many updates
    if payload.function_ids is not None:
        # Replace junction rows without triggering lazy-load
        await db.execute(
            delete(visit_functions).where(visit_functions.c.visit_id == visit.id)
        )
        if payload.function_ids:
            await db.execute(
                insert(visit_functions),
                [
                    {"visit_id": visit.id, "function_id": fid}
                    for fid in payload.function_ids
                ],
            )
    if payload.species_ids is not None:
        await db.execute(
            delete(visit_species).where(visit_species.c.visit_id == visit.id)
        )
        if payload.species_ids:
            await db.execute(
                insert(visit_species),
                [
                    {"visit_id": visit.id, "species_id": sid}
                    for sid in payload.species_ids
                ],
            )

    await db.commit()
    # Re-fetch with eager loading to avoid lazy-load (MissingGreenlet) in response
    stmt = (
        select(Visit)
        .where(Visit.id == visit.id)
        .options(
            selectinload(Visit.functions),
            selectinload(Visit.species),
            selectinload(Visit.researchers),
        )
    )
    visit_loaded = (await db.execute(stmt)).scalars().first()
    return visit_loaded or visit


@router.delete(
    "/{visit_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response
)
async def delete_visit(_: AdminDep, db: DbDep, visit_id: int) -> Response:
    """Delete a visit by id."""

    visit = await db.get(Visit, visit_id)
    if visit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await db.delete(visit)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
