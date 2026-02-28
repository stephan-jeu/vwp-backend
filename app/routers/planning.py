from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Query, HTTPException, status
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from app.models.visit import Visit
from app.models.cluster import Cluster
from app.models.user import User
from app.schemas.planning import PlanningVisitRead, PlanningGenerateRequest
from app.deps import AdminDep, DbDep
from app.db.utils import select_active
from app.services.activity_log_service import log_activity
from app.services.visit_planning_selection import select_visits_for_week
from app.services.planning_run_errors import PlanningRunError


_logger = logging.getLogger("uvicorn.error")


router = APIRouter()


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

    stmt = select_active(Visit).options(
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
            if (
                (getattr(v, "planned_week", None) == week)
                or (
                    getattr(v, "planned_week", None) is None
                    and getattr(v, "provisional_week", None) == week
                )
            )
        ]

    # Map to read items
    items: list[PlanningVisitRead] = []
    for v in planned:
        project_code = (
            getattr(getattr(v, "cluster", None), "project", None).code
            if getattr(v, "cluster", None) and getattr(v.cluster, "project", None)
            else ""
        )
        cluster_number = getattr(getattr(v, "cluster", None), "cluster_number", "")
        functions = [f.name for f in (v.functions or []) if getattr(f, "name", None)]
        species = [s.name for s in (v.species or []) if getattr(s, "name", None)]
        researchers = [u.full_name or "" for u in (v.researchers or [])]

        items.append(
            PlanningVisitRead(
                id=v.id,
                project_code=project_code,
                cluster_number=cluster_number or "",
                functions=sorted(set(functions)),
                species=sorted(set(species)),
                from_date=v.from_date,
                to_date=v.to_date,
                planned_date=v.planned_date,
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
    simulated_today: Annotated[date | None, Query()] = None,
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
    today = simulated_today or date.today()
    current_year = today.year
    week_monday = date.fromisocalendar(current_year, week, 1)
    # Use dynamic timeout (None) which defaults to max(5s, min(60s, complexity))
    # Include travel time optimization
    try:
        result = await select_visits_for_week(
            db, week_monday, timeout_seconds=None, include_travel_time=True, today=today
        )
    except PlanningRunError as exc:
        _logger.exception("PlanningRunError: %s", exc)
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Het is niet gelukt om een goede planning te maken. "
                "Probeer het nog een keer of doe de planning voor deze week handmatig."
            ),
        ) from exc
    except Exception as exc:
        _logger.exception("Unexpected error during planning generation: %s", exc)
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Het is niet gelukt om een goede planning te maken. "
                "Probeer het nog een keer of doe de planning voor deze week handmatig."
            ),
        ) from exc

    # Post-planning Sanitization: Check for future conflicts
    from app.services.visit_sanitization import sanitize_future_planning
    from core.settings import get_settings

    sanitized = await sanitize_future_planning(
        db, week_monday, result.get("selected_visit_ids", [])
    )
    if sanitized:
        result["sanitized_future_visit_ids"] = sanitized

    selected_ids = result.get("selected_visit_ids", [])

    await log_activity(
        db,
        actor_id=admin.id,
        action="planning_generated",
        target_type="planning_week",
        target_id=week,
        details={
            "week": week,
            "year": current_year,
            "selected_visit_ids": selected_ids,
            "skipped_visit_ids": result.get("skipped_visit_ids", []),
            "sanitized_future_visit_ids": sanitized,
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

    stmt = select_active(Visit)
    if week is not None:
        week_start, week_end = _work_week_bounds(date.today().year, week)
        stmt = stmt.where(
            # Target visits explicitly planned for this week OR occurring in this week
            # We want to clear "Planning" which implies mapped to a week.
            # So targets:
            # 1. planned_week == week
            # 2. OR planned_week is None AND provisional_week == week
            (Visit.planned_week == week)
            | and_(
                Visit.planned_week.is_(None),
                Visit.provisional_week == week,
            )
        ).options(selectinload(Visit.researchers))
    else:
        stmt = stmt.options(selectinload(Visit.researchers))

    # Protect Manual/Custom visits from being cleared
    stmt = stmt.where(
        and_(
            Visit.custom_function_name.is_(None),
            Visit.custom_species_name.is_(None),
            Visit.planning_locked.is_(False),
        )
    )

    visits: list[Visit] = (await db.execute(stmt)).scalars().unique().all()
    for v in visits:
        v.researchers.clear()
        v.planned_week = None
        v.planned_date = None

    await db.commit()

    return {"cleared": len(visits)}


@router.post("/{year}/{week}/notify")
async def notify_planning(
    admin: AdminDep,
    db: DbDep,
    year: int,
    week: int,
) -> dict:
    """Send email notifications to researchers for their planned visits in this week."""
    from app.services.planning_notification_service import send_planning_emails_for_week

    result = await send_planning_emails_for_week(db, week, year)
    
    if result["total"] == 0:
        return {"message": "Geen onderzoekers met geplande bezoeken gevonden voor deze week.", "stats": result}
        
    return {
        "message": f"Emails verstuurd: {result['sent']} van {result['total']} ({result['failed']} mislukt)",
        "stats": result
    }
