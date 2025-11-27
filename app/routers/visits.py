from __future__ import annotations

from typing import Annotated
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import delete, insert, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cluster import Cluster
from app.models.project import Project
from app.models.species import Species
from app.models.user import User
from app.models.visit import Visit, visit_functions, visit_species, visit_researchers
from app.models.activity_log import ActivityLog
from app.schemas.function import FunctionCompactRead
from app.schemas.species import SpeciesCompactRead
from app.schemas.user import UserNameRead
from app.schemas.activity_log import ActivityLogRead
from app.schemas.visit import (
    VisitAdvertisedRequest,
    VisitAdminPlanningStatusRequest,
    VisitApprovalRequest,
    VisitCancelRequest,
    VisitCreate,
    VisitExecuteDeviationRequest,
    VisitExecuteRequest,
    VisitListResponse,
    VisitListRow,
    VisitNotExecutedRequest,
    VisitRead,
    VisitRejectionRequest,
    VisitUpdate,
)
from app.services.activity_log_service import log_activity
from app.services.security import get_current_user, require_admin
from app.services.soft_delete import soft_delete_entity
from app.services.visit_planning_selection import _qualifies_user_for_visit
from app.services.visit_status_service import (
    VisitStatusCode,
    resolve_visit_status,
    resolve_visit_status_by_id,
)
from app.services.visit_execution_updates import update_subsequent_visits
from core.settings import get_settings
from db.session import get_db

router = APIRouter()


DbDep = Annotated[AsyncSession, Depends(get_db)]
AdminDep = Annotated[User, Depends(require_admin)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.get("", response_model=VisitListResponse)
async def list_visits(
    current_user: UserDep,
    db: DbDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    search: Annotated[str | None, Query()] = None,
    statuses: Annotated[list[VisitStatusCode] | None, Query()] = None,
    simulated_today: Annotated[date | None, Query()] = None,
) -> VisitListResponse:
    """Return a paginated list of visits for the overview table.

    The listing is available to any authenticated user. Filters and
    ordering are applied in-memory after loading the necessary
    relationships to keep the implementation straightforward while
    still avoiding lazy-loading at response time.

    Args:
        current_user: Ensures the caller is authenticated (admin or researcher).
        db: Async SQLAlchemy session.
        page: 1-based page number.
        page_size: Page size (max 200).
        search: Optional free-text search term applied across project
            code/location, cluster address/number, functions, species
            and researcher names.
        statuses: Optional list of lifecycle status codes to filter by.

    Returns:
        Paginated :class:`VisitListResponse` with flattened rows.
    """

    settings = get_settings()
    effective_today: date | None = None
    if settings.test_mode_enabled and getattr(current_user, "admin", False):
        effective_today = simulated_today

    stmt = select(Visit).options(
        selectinload(Visit.cluster).selectinload(Cluster.project),
        selectinload(Visit.functions),
        selectinload(Visit.species),
        selectinload(Visit.researchers),
        selectinload(Visit.preferred_researcher),
    )
    visits = (await db.execute(stmt)).scalars().all()

    # Optional text search across project, cluster and related names
    if search:
        term = search.strip().lower()

        def _matches(v: Visit) -> bool:
            cluster = v.cluster
            project: Project | None = getattr(cluster, "project", None)
            if project and (
                term in project.code.lower() or term in project.location.lower()
            ):
                return True

            if cluster and (
                term in cluster.address.lower() or term in str(cluster.cluster_number)
            ):
                return True

            for f in v.functions:
                if term in (f.name or "").lower():
                    return True
            for s in v.species:
                if (
                    term in (s.name or "").lower()
                    or term in (s.abbreviation or "").lower()
                ):
                    return True
            for r in v.researchers:
                if term in (r.full_name or "").lower():
                    return True

            return False

        visits = [v for v in visits if _matches(v)]

    # Derive lifecycle status for each visit once, then filter by status
    status_map: dict[int, VisitStatusCode] = {}
    for v in visits:
        status_map[v.id] = await resolve_visit_status(db, v, today=effective_today)

    if statuses:
        allowed = set(statuses)
        visits = [v for v in visits if status_map.get(v.id) in allowed]

    # Order by start date and project code (cluster/visit as tie-breakers)
    def _sort_key(v: Visit) -> tuple:
        cluster = v.cluster
        project: Project | None = getattr(cluster, "project", None)
        from_date = v.from_date or date.max
        project_code = project.code if project else ""
        cluster_number = cluster.cluster_number if cluster else 0
        visit_nr = v.visit_nr or 0
        return (from_date, project_code, cluster_number, visit_nr)

    visits.sort(key=_sort_key)

    total = len(visits)
    start = (page - 1) * page_size
    end = start + page_size
    page_items = visits[start:end]

    items = []
    for v in page_items:
        cluster = v.cluster
        project = getattr(cluster, "project", None)
        project_code = project.code if project else ""
        project_location = project.location if project else ""
        status = status_map.get(v.id, VisitStatusCode.CREATED)

        items.append(
            {
                "id": v.id,
                "project_code": project_code,
                "project_location": project_location,
                "project_google_drive_folder": (
                    project.google_drive_folder if project else None
                ),
                "cluster_id": cluster.id if cluster else 0,
                "cluster_number": cluster.cluster_number if cluster else 0,
                "cluster_address": cluster.address if cluster else "",
                "status": status,
                "function_ids": [f.id for f in v.functions],
                "species_ids": [s.id for s in v.species],
                "functions": [
                    FunctionCompactRead(id=f.id, name=f.name) for f in v.functions
                ],
                "species": [
                    SpeciesCompactRead(
                        id=s.id, name=s.name, abbreviation=s.abbreviation
                    )
                    for s in v.species
                ],
                "required_researchers": v.required_researchers,
                "visit_nr": v.visit_nr,
                "planned_week": v.planned_week,
                "from_date": v.from_date,
                "to_date": v.to_date,
                "duration": v.duration,
                "min_temperature_celsius": v.min_temperature_celsius,
                "max_wind_force_bft": v.max_wind_force_bft,
                "max_precipitation": v.max_precipitation,
                "expertise_level": v.expertise_level,
                "wbc": v.wbc,
                "fiets": v.fiets,
                "hub": v.hub,
                "dvp": v.dvp,
                "sleutel": v.sleutel,
                "remarks_planning": v.remarks_planning,
                "remarks_field": v.remarks_field,
                "priority": v.priority,
                "part_of_day": v.part_of_day,
                "start_time_text": v.start_time_text,
                "preferred_researcher_id": v.preferred_researcher_id,
                "preferred_researcher": (
                    None
                    if v.preferred_researcher is None
                    else UserNameRead(
                        id=v.preferred_researcher.id,
                        full_name=v.preferred_researcher.full_name,
                    )
                ),
                "researchers": [
                    UserNameRead(id=r.id, full_name=r.full_name) for r in v.researchers
                ],
                "advertized": v.advertized,
                "quote": v.quote,
            }
        )

    return VisitListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{visit_id}", response_model=VisitListRow)
async def get_visit_detail(
    current_user: UserDep,
    db: DbDep,
    visit_id: int,
    simulated_today: Annotated[date | None, Query()] = None,
) -> VisitListRow:
    """Return detailed information for a single visit.

    The payload matches :class:`VisitListRow` used by the overview table,
    so the frontend can reuse the same data model for detail views.
    """

    settings = get_settings()
    effective_today: date | None = None
    if settings.test_mode_enabled and getattr(current_user, "admin", False):
        effective_today = simulated_today

    stmt = (
        select(Visit)
        .where(Visit.id == visit_id)
        .options(
            selectinload(Visit.cluster).selectinload(Cluster.project),
            selectinload(Visit.functions),
            selectinload(Visit.species),
            selectinload(Visit.researchers),
            selectinload(Visit.preferred_researcher),
        )
    )
    visit = (await db.execute(stmt)).scalars().first()
    if visit is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Visit not found"
        )

    status = await resolve_visit_status(db, visit, today=effective_today)
    cluster = visit.cluster
    project: Project | None = getattr(cluster, "project", None)
    project_code = project.code if project else ""
    project_location = project.location if project else ""
    project_google_drive_folder = project.google_drive_folder if project else None

    return VisitListRow(
        id=visit.id,
        project_code=project_code,
        project_location=project_location,
        project_google_drive_folder=project_google_drive_folder,
        cluster_id=cluster.id if cluster else 0,
        cluster_number=cluster.cluster_number if cluster else 0,
        cluster_address=cluster.address if cluster else "",
        status=status,
        function_ids=[f.id for f in visit.functions],
        species_ids=[s.id for s in visit.species],
        functions=[FunctionCompactRead(id=f.id, name=f.name) for f in visit.functions],
        species=[
            SpeciesCompactRead(
                id=s.id,
                name=s.name,
                abbreviation=s.abbreviation,
            )
            for s in visit.species
        ],
        required_researchers=visit.required_researchers,
        visit_nr=visit.visit_nr,
        from_date=visit.from_date,
        to_date=visit.to_date,
        duration=visit.duration,
        min_temperature_celsius=visit.min_temperature_celsius,
        max_wind_force_bft=visit.max_wind_force_bft,
        max_precipitation=visit.max_precipitation,
        expertise_level=visit.expertise_level,
        wbc=visit.wbc,
        fiets=visit.fiets,
        hub=visit.hub,
        dvp=visit.dvp,
        sleutel=visit.sleutel,
        remarks_planning=visit.remarks_planning,
        remarks_field=visit.remarks_field,
        priority=visit.priority,
        part_of_day=visit.part_of_day,
        start_time_text=visit.start_time_text,
        preferred_researcher_id=visit.preferred_researcher_id,
        preferred_researcher=(
            None
            if visit.preferred_researcher is None
            else UserNameRead(
                id=visit.preferred_researcher.id,
                full_name=visit.preferred_researcher.full_name,
            )
        ),
        researchers=[
            UserNameRead(id=r.id, full_name=r.full_name) for r in visit.researchers
        ],
        advertized=visit.advertized,
        quote=visit.quote,
    )


@router.post("", response_model=VisitRead)
async def create_visit(
    admin: AdminDep,
    db: DbDep,
    payload: VisitCreate,
) -> Visit:
    """Create a new visit with provided fields."""

    data = payload.dict(
        exclude_unset=True,
        exclude={"function_ids", "species_ids", "researcher_ids"},
    )
    visit = Visit(**data)
    db.add(visit)
    await db.flush()

    # Handle many-to-many relations on creation
    if payload.function_ids:
        await db.execute(
            insert(visit_functions),
            [
                {"visit_id": visit.id, "function_id": fid}
                for fid in payload.function_ids
            ],
        )
    if payload.species_ids:
        await db.execute(
            insert(visit_species),
            [{"visit_id": visit.id, "species_id": sid} for sid in payload.species_ids],
        )
    if payload.researcher_ids:
        await db.execute(
            insert(visit_researchers),
            [{"visit_id": visit.id, "user_id": rid} for rid in payload.researcher_ids],
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


@router.get("/advertised/list", response_model=list[VisitListRow])
async def list_advertised_visits(
    user: UserDep,
    db: DbDep,
    simulated_today: Annotated[date | None, Query()] = None,
) -> list[VisitListRow]:
    """Return all currently advertised visits available for takeover.

    Visits are included when their ``advertized`` flag is true and their derived
    lifecycle status is either ``planned`` or ``not_executed``. The response
    includes the user who most recently advertised the visit and a boolean flag
    indicating whether the current user qualifies to accept the visit.
    """

    settings = get_settings()
    effective_today: date | None = None
    if settings.test_mode_enabled and getattr(user, "admin", False):
        effective_today = simulated_today

    stmt = (
        select(Visit)
        .where(Visit.advertized.is_(True))
        .options(
            selectinload(Visit.cluster).selectinload(Cluster.project),
            selectinload(Visit.functions),
            selectinload(Visit.species).selectinload(Species.family),
            selectinload(Visit.researchers),
            selectinload(Visit.preferred_researcher),
        )
    )
    visits = (await db.execute(stmt)).scalars().all()
    if not visits:
        return []

    status_map: dict[int, VisitStatusCode] = {}
    for v in visits:
        status_map[v.id] = await resolve_visit_status(db, v, today=effective_today)

    allowed_statuses: set[VisitStatusCode] = {
        VisitStatusCode.PLANNED,
        VisitStatusCode.NOT_EXECUTED,
    }
    visits = [v for v in visits if status_map.get(v.id) in allowed_statuses]
    if not visits:
        return []

    visit_ids = [v.id for v in visits]

    stmt_logs = (
        select(ActivityLog)
        .where(
            ActivityLog.target_type == "visit",
            ActivityLog.target_id.in_(visit_ids),
            ActivityLog.action == "visit_advertised",
        )
        .options(selectinload(ActivityLog.actor))
        .order_by(ActivityLog.target_id, ActivityLog.created_at.desc())
    )
    logs = (await db.execute(stmt_logs)).scalars().all()

    advertised_by_map: dict[int, ActivityLog] = {}
    for log in logs:
        if log.target_id is None:
            continue
        if log.target_id in advertised_by_map:
            continue
        advertised_by_map[log.target_id] = log

    items: list[VisitListRow] = []
    user_id = getattr(user, "id", None)

    for v in visits:
        cluster = v.cluster
        project: Project | None = getattr(cluster, "project", None)
        project_code = project.code if project else ""
        project_location = project.location if project else ""
        status = status_map.get(v.id, VisitStatusCode.CREATED)

        log = advertised_by_map.get(v.id)
        advertised_by = None
        if log is not None and log.actor is not None:
            advertised_by = UserNameRead(id=log.actor.id, full_name=log.actor.full_name)

        can_accept = False
        if user_id is not None:
            if _qualifies_user_for_visit(user, v) and all(
                getattr(r, "id", None) != user_id for r in (v.researchers or [])
            ):
                can_accept = True

        items.append(
            VisitListRow(
                id=v.id,
                project_code=project_code,
                project_location=project_location,
                project_google_drive_folder=(
                    project.google_drive_folder if project else None
                ),
                cluster_id=cluster.id if cluster else 0,
                cluster_number=cluster.cluster_number if cluster else 0,
                cluster_address=cluster.address if cluster else "",
                status=status,
                function_ids=[f.id for f in v.functions],
                species_ids=[s.id for s in v.species],
                functions=[
                    FunctionCompactRead(id=f.id, name=f.name) for f in v.functions
                ],
                species=[
                    SpeciesCompactRead(
                        id=s.id,
                        name=s.name,
                        abbreviation=s.abbreviation,
                    )
                    for s in v.species
                ],
                required_researchers=v.required_researchers,
                visit_nr=v.visit_nr,
                planned_week=v.planned_week,
                from_date=v.from_date,
                to_date=v.to_date,
                duration=v.duration,
                min_temperature_celsius=v.min_temperature_celsius,
                max_wind_force_bft=v.max_wind_force_bft,
                max_precipitation=v.max_precipitation,
                expertise_level=v.expertise_level,
                wbc=v.wbc,
                fiets=v.fiets,
                hub=v.hub,
                dvp=v.dvp,
                sleutel=v.sleutel,
                remarks_planning=v.remarks_planning,
                remarks_field=v.remarks_field,
                priority=v.priority,
                part_of_day=v.part_of_day,
                start_time_text=v.start_time_text,
                preferred_researcher_id=v.preferred_researcher_id,
                preferred_researcher=(
                    None
                    if v.preferred_researcher is None
                    else UserNameRead(
                        id=v.preferred_researcher.id,
                        full_name=v.preferred_researcher.full_name,
                    )
                ),
                researchers=[
                    UserNameRead(id=r.id, full_name=r.full_name) for r in v.researchers
                ],
                advertized=v.advertized,
                quote=v.quote,
                advertized_by=advertised_by,
                can_accept=can_accept,
            )
        )

    return items


@router.get("/{visit_id}/activity", response_model=list[ActivityLogRead])
async def list_visit_activity(
    _: UserDep,
    db: DbDep,
    visit_id: int,
) -> list[ActivityLogRead]:
    """Return activity log entries related to a single visit.

    Entries are filtered by ``target_type="visit"`` and the given
    ``visit_id`` and ordered from newest to oldest so the most recent
    actions are visible first in the UI.

    Args:
        _: Ensures the caller is authenticated.
        db: Async SQLAlchemy session.
        visit_id: Primary key of the visit whose activity we want.

    Returns:
        List of :class:`ActivityLogRead` entries.
    """

    stmt = (
        select(ActivityLog)
        .where(
            ActivityLog.target_type == "visit",
            ActivityLog.target_id == visit_id,
        )
        .options(selectinload(ActivityLog.actor))
        .order_by(ActivityLog.created_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.put("/{visit_id}", response_model=VisitRead)
async def update_visit(
    admin: AdminDep, db: DbDep, visit_id: int, payload: VisitUpdate
) -> Visit:
    """Update a visit with provided fields.

    For now we accept the VisitRead payload to keep implementation minimal; in a
    follow-up we can tighten this to a dedicated VisitUpdate schema.
    """

    visit = await db.get(Visit, visit_id)
    if visit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    old_advertized = bool(getattr(visit, "advertized", False))

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
        "hub",
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

    new_advertized = bool(getattr(visit, "advertized", False))
    if payload.advertized is not None and new_advertized != old_advertized:
        action = "visit_advertised" if new_advertized else "visit_advertised_cancelled"
        await log_activity(
            db,
            actor_id=admin.id,
            action=action,
            target_type="visit",
            target_id=visit.id,
            details=None,
            commit=False,
        )

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
    if payload.researcher_ids is not None:
        await db.execute(
            delete(visit_researchers).where(visit_researchers.c.visit_id == visit.id)
        )
        if payload.researcher_ids:
            await db.execute(
                insert(visit_researchers),
                [
                    {"visit_id": visit.id, "user_id": rid}
                    for rid in payload.researcher_ids
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


async def _get_visit_for_status_change(db: AsyncSession, visit_id: int) -> Visit:
    stmt = (
        select(Visit)
        .where(Visit.id == visit_id)
        .options(selectinload(Visit.researchers))
    )
    visit = (await db.execute(stmt)).scalars().first()
    if visit is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Visit not found"
        )
    return visit


@router.post(
    "/{visit_id}/execute",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def execute_visit(
    user: UserDep,
    db: DbDep,
    visit_id: int,
    payload: VisitExecuteRequest,
) -> Response:
    """Mark a visit as executed without protocol deviation."""

    visit = await _get_visit_for_status_change(db, visit_id)

    if not user.admin and all(r.id != user.id for r in visit.researchers):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    await log_activity(
        db,
        actor_id=user.id,
        action="visit_executed",
        target_type="visit",
        target_id=visit_id,
        details={
            "execution_date": payload.execution_date.isoformat(),
            "comment": payload.comment,
        },
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{visit_id}/admin-planning-status",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def set_admin_planning_status(
    admin: AdminDep,
    db: DbDep,
    visit_id: int,
    payload: VisitAdminPlanningStatusRequest,
) -> Response:
    """Adjust the planning-oriented status for a visit as an admin.

    This endpoint allows admins to reset a visit back to an "open" state by
    clearing researchers and planned week, or to mark it as "planned" by
    assigning a week and researchers. In both cases an audit log entry with
    ``action="visit_status_cleared"`` is created so that the derived
    lifecycle status is recomputed based on the updated planning data.
    """

    visit = await db.get(Visit, visit_id)
    if visit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    mode = (payload.mode or "").strip().lower()
    if mode not in {"open", "planned"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="mode must be 'open' or 'planned'",
        )

    previous_status = await resolve_visit_status_by_id(db, visit_id)

    if mode == "open":
        visit.planned_week = None
        await db.execute(
            delete(visit_researchers).where(visit_researchers.c.visit_id == visit.id)
        )
        planned_week = None
        researcher_ids: list[int] | None = None
    else:
        if payload.planned_week is None or payload.researcher_ids is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "planned_week and researcher_ids are required when "
                    "mode is 'planned'"
                ),
            )

        visit.planned_week = payload.planned_week
        await db.execute(
            delete(visit_researchers).where(visit_researchers.c.visit_id == visit.id)
        )
        if payload.researcher_ids:
            await db.execute(
                insert(visit_researchers),
                [
                    {"visit_id": visit.id, "user_id": rid}
                    for rid in payload.researcher_ids
                ],
            )
        planned_week = payload.planned_week
        researcher_ids = list(payload.researcher_ids)

    await log_activity(
        db,
        actor_id=admin.id,
        action="visit_status_cleared",
        target_type="visit",
        target_id=visit.id,
        details={
            "mode": mode,
            "previous_status": (
                None if previous_status is None else previous_status.value
            ),
            "planned_week": planned_week,
            "researcher_ids": researcher_ids,
            "comment": payload.comment,
        },
        commit=False,
    )

    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{visit_id}/advertised",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def set_visit_advertised(
    user: UserDep,
    db: DbDep,
    visit_id: int,
    payload: VisitAdvertisedRequest,
) -> Response:
    """Toggle the advertised flag for a visit.

    Both admins and researchers assigned to the visit may change the
    advertised state. When the flag changes we emit a corresponding
    activity log entry (``visit_advertised`` or
    ``visit_advertised_cancelled``).
    """

    visit = await _get_visit_for_status_change(db, visit_id)

    if not user.admin and all(r.id != user.id for r in visit.researchers):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    old_advertized = bool(getattr(visit, "advertized", False))
    new_advertized = bool(payload.advertised)

    if new_advertized == old_advertized:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    visit.advertized = new_advertized

    action = "visit_advertised" if new_advertized else "visit_advertised_cancelled"
    await log_activity(
        db,
        actor_id=user.id,
        action=action,
        target_type="visit",
        target_id=visit.id,
        details=None,
        commit=False,
    )

    # Update subsequent visits
    if payload.execution_date:
        await update_subsequent_visits(db, visit, payload.execution_date)

    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/audit/list", response_model=list[VisitListRow])
async def list_visits_for_audit(
    _: AdminDep,
    db: DbDep,
    simulated_today: Annotated[date | None, Query()] = None,
) -> list[VisitListRow]:
    """Return all visits that are relevant for admin audit.

    The listing is restricted to admins and includes all visits whose
    lifecycle status indicates that a visit was executed (with or
    without deviation). The result is not paginated as the expected
    volume is manageable for the audit workflow.

    Args:
        _: Ensures the caller is an admin user.
        db: Async SQLAlchemy session.

    Returns:
        List of :class:`VisitListRow` entries for visits that require or
        have undergone audit.
    """

    settings = get_settings()
    effective_today: date | None = None
    if settings.test_mode_enabled:
        effective_today = simulated_today
    stmt = select(Visit).options(
        selectinload(Visit.cluster).selectinload(Cluster.project),
        selectinload(Visit.functions),
        selectinload(Visit.species),
        selectinload(Visit.researchers),
        selectinload(Visit.preferred_researcher),
    )
    visits = (await db.execute(stmt)).scalars().all()

    status_map: dict[int, VisitStatusCode] = {}
    for v in visits:
        status_map[v.id] = await resolve_visit_status(db, v)

    relevant_statuses: set[VisitStatusCode] = {
        VisitStatusCode.EXECUTED,
        VisitStatusCode.EXECUTED_WITH_DEVIATION,
    }
    visits = [v for v in visits if status_map.get(v.id) in relevant_statuses]

    execution_logs: dict[int, ActivityLog] = {}
    if visits:
        visit_ids = [v.id for v in visits]
        stmt_logs = (
            select(ActivityLog)
            .where(
                ActivityLog.target_type == "visit",
                ActivityLog.target_id.in_(visit_ids),
                ActivityLog.action.in_(
                    {"visit_executed", "visit_executed_with_deviation"}
                ),
            )
            .order_by(ActivityLog.target_id, ActivityLog.created_at.desc())
        )
        log_rows = (await db.execute(stmt_logs)).scalars().all()
        for log in log_rows:
            if log.target_id is None:
                continue
            if log.target_id in execution_logs:
                continue
            execution_logs[log.target_id] = log

    def _sort_key(v: Visit) -> tuple:
        cluster = v.cluster
        project: Project | None = getattr(cluster, "project", None)
        from_date = v.from_date or date.max
        project_code = project.code if project else ""
        cluster_number = cluster.cluster_number if cluster else 0
        visit_nr = v.visit_nr or 0
        return (from_date, project_code, cluster_number, visit_nr)

    visits.sort(key=_sort_key)

    items: list[VisitListRow] = []
    for v in visits:
        cluster = v.cluster
        project: Project | None = getattr(cluster, "project", None)
        project_code = project.code if project else ""
        project_location = project.location if project else ""
        status = status_map.get(v.id, VisitStatusCode.CREATED)

        execution_date = None
        log = execution_logs.get(v.id)
        if log is not None and log.details:
            raw_date = log.details.get("execution_date")
            if isinstance(raw_date, str):
                try:
                    execution_date = date.fromisoformat(raw_date)
                except ValueError:
                    execution_date = None

        items.append(
            VisitListRow(
                id=v.id,
                project_code=project_code,
                project_location=project_location,
                project_google_drive_folder=(
                    project.google_drive_folder if project else None
                ),
                cluster_id=cluster.id if cluster else 0,
                cluster_number=cluster.cluster_number if cluster else 0,
                cluster_address=cluster.address if cluster else "",
                status=status,
                function_ids=[f.id for f in v.functions],
                species_ids=[s.id for s in v.species],
                functions=[
                    FunctionCompactRead(id=f.id, name=f.name) for f in v.functions
                ],
                species=[
                    SpeciesCompactRead(
                        id=s.id,
                        name=s.name,
                        abbreviation=s.abbreviation,
                    )
                    for s in v.species
                ],
                required_researchers=v.required_researchers,
                visit_nr=v.visit_nr,
                planned_week=v.planned_week,
                from_date=v.from_date,
                to_date=v.to_date,
                duration=v.duration,
                execution_date=execution_date,
                min_temperature_celsius=v.min_temperature_celsius,
                max_wind_force_bft=v.max_wind_force_bft,
                max_precipitation=v.max_precipitation,
                expertise_level=v.expertise_level,
                wbc=v.wbc,
                fiets=v.fiets,
                hub=v.hub,
                dvp=v.dvp,
                sleutel=v.sleutel,
                remarks_planning=v.remarks_planning,
                remarks_field=v.remarks_field,
                priority=v.priority,
                part_of_day=v.part_of_day,
                start_time_text=v.start_time_text,
                preferred_researcher_id=v.preferred_researcher_id,
                preferred_researcher=(
                    None
                    if v.preferred_researcher is None
                    else UserNameRead(
                        id=v.preferred_researcher.id,
                        full_name=v.preferred_researcher.full_name,
                    )
                ),
                researchers=[
                    UserNameRead(id=r.id, full_name=r.full_name) for r in v.researchers
                ],
                advertized=v.advertized,
                quote=v.quote,
            )
        )

    return items


@router.post(
    "/{visit_id}/execute-deviation",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def execute_visit_with_deviation(
    user: UserDep,
    db: DbDep,
    visit_id: int,
    payload: VisitExecuteDeviationRequest,
) -> Response:
    """Mark a visit as executed with a protocol deviation."""

    visit = await _get_visit_for_status_change(db, visit_id)

    if not user.admin and all(r.id != user.id for r in visit.researchers):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    await log_activity(
        db,
        actor_id=user.id,
        action="visit_executed_with_deviation",
        target_type="visit",
        target_id=visit_id,
        details={
            "execution_date": payload.execution_date.isoformat(),
            "reason": payload.reason,
            "comment": payload.comment,
        },
    )

    # Update subsequent visits
    if payload.execution_date:
        await update_subsequent_visits(db, visit, payload.execution_date)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{visit_id}/not-executed",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def mark_visit_not_executed(
    user: UserDep,
    db: DbDep,
    visit_id: int,
    payload: VisitNotExecutedRequest,
) -> Response:
    """Mark a visit as not executed."""

    visit = await _get_visit_for_status_change(db, visit_id)

    if not user.admin and all(r.id != user.id for r in visit.researchers):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    await log_activity(
        db,
        actor_id=user.id,
        action="visit_not_executed",
        target_type="visit",
        target_id=visit_id,
        details={
            "date": payload.date.isoformat(),
            "reason": payload.reason,
        },
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{visit_id}/approve",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def approve_visit(
    admin: AdminDep,
    db: DbDep,
    visit_id: int,
    payload: VisitApprovalRequest,
) -> Response:
    """Approve a visit result."""

    visit = await db.get(Visit, visit_id)
    if visit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    await log_activity(
        db,
        actor_id=admin.id,
        action="visit_approved",
        target_type="visit",
        target_id=visit_id,
        details={
            "comment": payload.comment,
            "audit": None if payload.audit is None else payload.audit.model_dump(),
        },
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{visit_id}/reject",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def reject_visit(
    admin: AdminDep,
    db: DbDep,
    visit_id: int,
    payload: VisitRejectionRequest,
) -> Response:
    """Reject a visit result."""

    visit = await db.get(Visit, visit_id)
    if visit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    await log_activity(
        db,
        actor_id=admin.id,
        action="visit_rejected",
        target_type="visit",
        target_id=visit_id,
        details={
            "reason": payload.reason,
            "audit": None if payload.audit is None else payload.audit.model_dump(),
        },
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{visit_id}/cancel",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def cancel_visit(
    admin: AdminDep,
    db: DbDep,
    visit_id: int,
    payload: VisitCancelRequest,
) -> Response:
    """Cancel a visit."""

    visit = await db.get(Visit, visit_id)
    if visit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    await log_activity(
        db,
        actor_id=admin.id,
        action="visit_cancelled",
        target_type="visit",
        target_id=visit_id,
        details={
            "reason": payload.reason,
        },
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{visit_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response
)
async def delete_visit(_: AdminDep, db: DbDep, visit_id: int) -> Response:
    """Delete a visit by id."""

    visit = await db.get(Visit, visit_id)
    if visit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await soft_delete_entity(db, visit, cascade=False)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{visit_id}/accept-advertised",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def accept_advertised_visit(
    user: UserDep,
    db: DbDep,
    visit_id: int,
) -> Response:
    """Accept an advertised visit and reassign researchers.

    The current user must qualify for the visit according to the same rules used
    by the planner. When accepted, the user is added as a researcher (if not
    already present), the original advertiser is removed when known and the
    advertised flag is cleared. Corresponding activity log entries are added
    for auditing.
    """

    stmt = (
        select(Visit)
        .where(Visit.id == visit_id)
        .options(
            selectinload(Visit.researchers),
            selectinload(Visit.functions),
            selectinload(Visit.species).selectinload(Species.family),
            selectinload(Visit.cluster).selectinload(Cluster.project),
        )
    )
    visit = (await db.execute(stmt)).scalars().first()
    if visit is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Visit not found"
        )

    if not visit.advertized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Visit is not advertised for takeover",
        )

    status_code_value = await resolve_visit_status(db, visit)
    if status_code_value not in {
        VisitStatusCode.PLANNED,
        VisitStatusCode.NOT_EXECUTED,
    }:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Visit is not in a state that allows takeover",
        )

    if not _qualifies_user_for_visit(user, visit):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    user_id = getattr(user, "id", None)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    stmt_log = (
        select(ActivityLog)
        .where(
            ActivityLog.target_type == "visit",
            ActivityLog.target_id == visit.id,
            ActivityLog.action == "visit_advertised",
        )
        .order_by(ActivityLog.created_at.desc())
        .limit(1)
    )
    latest_advertised_log = (await db.execute(stmt_log)).scalars().first()
    advertiser_id: int | None = None
    if latest_advertised_log is not None and latest_advertised_log.actor_id is not None:
        advertiser_id = latest_advertised_log.actor_id

    if advertiser_id is not None:
        await db.execute(
            delete(visit_researchers).where(
                visit_researchers.c.visit_id == visit.id,
                visit_researchers.c.user_id == advertiser_id,
            )
        )

    if all(getattr(r, "id", None) != user_id for r in (visit.researchers or [])):
        await db.execute(
            insert(visit_researchers),
            [{"visit_id": visit.id, "user_id": user_id}],
        )

    visit.advertized = False

    await log_activity(
        db,
        actor_id=user_id,
        action="visit_takeover_accepted",
        target_type="visit",
        target_id=visit.id,
        details={
            "previous_researcher_id": advertiser_id,
            "new_researcher_id": user_id,
        },
        commit=False,
    )
    await log_activity(
        db,
        actor_id=user_id,
        action="visit_advertised_cancelled",
        target_type="visit",
        target_id=visit.id,
        details=None,
        commit=False,
    )

    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
