from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.visit import Visit
from app.models.cluster import Cluster
from app.models.project import Project
from app.models.function import Function
from app.models.species import Species
from app.models.user import User
from app.schemas.planning import PlanningVisitRead, PlanningGenerateRequest
from app.services.activity_log_service import log_activity
from app.services.security import require_admin
from app.services.visit_planning_selection import select_visits_for_week
from db.session import get_db


router = APIRouter()


DbDep = Annotated[AsyncSession, Depends(get_db)]
AdminDep = Annotated[User, Depends(require_admin)]


def _work_week_bounds(current_year: int, iso_week: int) -> tuple[date, date]:
    monday = date.fromisocalendar(current_year, iso_week, 1)
    friday = monday + timedelta(days=4)
    return monday, friday


@router.get("", response_model=list[PlanningVisitRead])
async def get_planning(
    _: AdminDep,
    db: DbDep,
    week: int | None = Query(None, ge=1, le=53),
) -> list[PlanningVisitRead]:
    """Return planned visits (those that have at least one assigned researcher).

    If `week` is provided, limit to visits whose [from_date, to_date] overlap the
    work week (Mon–Fri) of the current year for the given ISO week.
    """

    stmt = select(Visit).options(
        selectinload(Visit.researchers),
        selectinload(Visit.functions),
        selectinload(Visit.species),
        selectinload(Visit.cluster).selectinload(Cluster.project),
    )

    visits: list[Visit] = (await db.execute(stmt)).scalars().unique().all()
    # Filter to planned (has researchers)
    planned = [v for v in visits if (v.researchers and len(v.researchers) > 0)]

    if week is not None:
        year = date.today().year
        week_start, week_end = _work_week_bounds(year, week)
        planned = [
            v
            for v in planned
            if (getattr(v, "from_date", None) and getattr(v, "to_date", None))
            and (v.from_date <= week_end and v.to_date >= week_start)
        ]

    # Map to read items
    items: list[PlanningVisitRead] = []
    for v in planned:
        project_code = (
            getattr(getattr(v, "cluster", None), "project", None).code
            if getattr(v, "cluster", None) and getattr(v.cluster, "project", None)
            else ""
        )
        cluster_number = getattr(getattr(v, "cluster", None), "cluster_number", 0)
        functions = [f.name for f in (v.functions or []) if getattr(f, "name", None)]
        species = [s.name for s in (v.species or []) if getattr(s, "name", None)]
        researchers = [u.full_name or "" for u in (v.researchers or [])]

        items.append(
            PlanningVisitRead(
                id=v.id,
                project_code=project_code,
                cluster_number=cluster_number or 0,
                functions=sorted(set(functions)),
                species=sorted(set(species)),
                from_date=v.from_date,
                to_date=v.to_date,
                researchers=[r for r in researchers if r],
            )
        )

    # Sort for stable UI: project, cluster, from_date
    items.sort(
        key=lambda it: (it.project_code, it.cluster_number, it.from_date or date.max)
    )
    return items


@router.post("/generate")
async def generate_planning(
    admin: AdminDep,
    db: DbDep,
    payload: PlanningGenerateRequest,
) -> dict:
    """Run the weekly selection to generate a planning preview for a given week.

    This does not assign researchers yet. It returns the selection summary
    (selected/skipped IDs) so the frontend can display or refresh the planned list.
    """

    week = payload.week
    if week < 1 or week > 53:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="week must be between 1 and 53",
        )

    # Compute Monday for current year ISO week
    current_year = date.today().year
    week_monday = date.fromisocalendar(current_year, week, 1)
    result = await select_visits_for_week(db, week_monday)

    await log_activity(
        db,
        actor_id=admin.id,
        action="planning_generated",
        target_type="planning_week",
        target_id=week,
        details={
            "week": week,
            "year": current_year,
            "selected_visit_ids": result.get("selected_visit_ids", []),
            "skipped_visit_ids": result.get("skipped_visit_ids", []),
            "capacity_remaining": result.get("capacity_remaining", {}),
        },
    )

    return result


@router.post("/clear")
async def clear_planned_researchers(
    _: AdminDep,
    db: DbDep,
    payload: PlanningGenerateRequest | None = None,
) -> dict:
    """Test-only helper to clear assigned researchers.

    If a week is provided, only visits overlapping that work week are affected.
    Otherwise all visits will be cleared.
    """

    week = getattr(payload, "week", None) if payload else None

    stmt = select(Visit)
    if week is not None:
        week_start, week_end = _work_week_bounds(date.today().year, week)
        stmt = stmt.where(
            and_(
                Visit.from_date <= week_end,
                Visit.to_date >= week_start,
            )
        ).options(selectinload(Visit.researchers))
    else:
        stmt = stmt.options(selectinload(Visit.researchers))

    visits: list[Visit] = (await db.execute(stmt)).scalars().unique().all()
    for v in visits:
        v.researchers.clear()

    await db.commit()

    return {"cleared": len(visits)}
