from __future__ import annotations

from typing import Annotated
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import and_, asc, case, delete, desc, extract, func, insert, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.cluster import Cluster
from app.models.function import Function
from app.models.project import Project
from app.models.protocol_visit_window import ProtocolVisitWindow  # noqa: F401 – kept for eager-loading references
from app.models.species import Species
from app.models.user import User
from app.models.visit import (
    Visit,
    visit_functions,
    visit_researchers,
    visit_species,
)
from app.models.activity_log import ActivityLog
from app.models.visit_audit import VisitAudit
from app.schemas.visit_audit import AuditStatus, VisitAuditRead, VisitAuditWrite
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
from app.deps import AdminDep, DbDep, UserDep
from app.services.activity_log_service import log_activity
from app.services.soft_delete import soft_delete_entity
from app.db.utils import select_active
from app.services.visit_planning_selection import _qualifies_user_for_visit
from app.services.visit_status_service import (
    VisitStatusCode,
    resolve_visit_status,
    resolve_visit_status_by_id,
    resolve_visit_statuses,
)
from app.services.visit_execution_updates import update_subsequent_visits
from app.services.visit_code_service import compute_visit_code
from app.services.pvw_sync_service import sync_cluster_pvw_links
from core.settings import get_settings

router = APIRouter()


def _isoweek_to_friday(year: int, week: int) -> date:
    try:
        return date.fromisocalendar(year, week, 5)
    except ValueError:
        return date.max


def _validate_planning_locked_payload(
    *,
    planning_locked: bool,
    planned_week: int | None,
    planned_date: "date | None" = None,
    researcher_ids: list[int] | None,
) -> None:
    if not planning_locked:
        return
    settings = get_settings()
    if settings.feature_daily_planning:
        if planned_date is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="planning_locked requires planned_date",
            )
    elif planned_week is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="planning_locked requires planned_week",
        )
    if not researcher_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="planning_locked requires at least one researcher",
        )


async def _validate_researchers_locked_payload(
    db: AsyncSession,
    *,
    researchers_locked: bool,
    researcher_ids: list[int] | None,
    visit: "Visit | None" = None,
) -> None:
    """Validate that researchers_locked constraints are satisfied.

    Raises HTTP 422 when:
    - researchers_locked is True but no researcher_ids are provided.
    - Any of the specified researchers do not exist.
    - The number of locked researchers does not match required_researchers.
    - Any locked researcher is not qualified for the visit.
    """
    if not researchers_locked:
        return
    effective_ids = researcher_ids or (
        [r.id for r in visit.researchers] if visit else []
    )
    if not effective_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="researchers_locked requires at least one researcher",
        )
    # Verify all specified researchers exist and are active
    stmt = select(User).where(
        User.id.in_(effective_ids),
        User.deleted_at.is_(None),
    )
    found = (await db.execute(stmt)).scalars().all()
    if len(found) != len(set(effective_ids)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="researchers_locked: one or more specified researchers were not found",
        )

    if visit is not None:
        # Check count matches required_researchers
        required = getattr(visit, "required_researchers", 1) or 1
        if len(set(effective_ids)) != required:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"researchers_locked: aantal vergrendelde onderzoekers ({len(set(effective_ids))}) "
                    f"komt niet overeen met het vereiste aantal onderzoekers ({required})"
                ),
            )



@router.get("/weeks", response_model=list[int])
async def list_available_weeks(
    current_user: UserDep,
    db: DbDep,
    mine: Annotated[bool, Query()] = False,
) -> list[int]:
    """Return a sorted list of unique ISO week numbers that have visits.

    Aggregates weeks from both `planned_week` (explicit) and `from_date` (implicit),
    returning a deduplicated, sorted list.
    """
    from app.models.visit import visit_researchers
    from app.models.availability import AvailabilityWeek

    stmt = select(Visit.planned_week, Visit.provisional_week)

    if mine:
        stmt = stmt.join(visit_researchers).where(
            visit_researchers.c.user_id == current_user.id
        )

    stmt = stmt.where(
        (Visit.planned_week.is_not(None)) | (Visit.provisional_week.is_not(None))
    )
    stmt = stmt.where(Visit.deleted_at.is_(None))

    rows = await db.execute(stmt)
    weeks = set()

    for p_week, prov_week in rows:
        target_week = p_week if p_week is not None else prov_week
        if target_week is not None and 1 <= target_week <= 53:
            weeks.add(target_week)

    # If listing for all (admin usage usually), also include weeks with availability
    if not mine:
        avail_stmt = (
            select(AvailabilityWeek.week)
            .join(User, AvailabilityWeek.user_id == User.id)
            .where(
                (AvailabilityWeek.morning_days > 0)
                | (AvailabilityWeek.daytime_days > 0)
                | (AvailabilityWeek.nighttime_days > 0)
                | (AvailabilityWeek.flex_days > 0)
            )
            .where(User.deleted_at.is_(None))
            .distinct()
        )
        avail_weeks = (await db.execute(avail_stmt)).scalars().all()
        weeks.update(avail_weeks)

    return sorted(list(weeks))


@router.get("/options/functions", response_model=list[FunctionCompactRead])
async def list_function_options(
    current_user: UserDep,
    db: DbDep,
) -> list[FunctionCompactRead]:
    """List all functions for selection menus.

    Args:
        current_user: Ensures the caller is authenticated.
        db: Async SQLAlchemy session.

    Returns:
        List of compact function objects.
    """

    _ = current_user
    stmt = select(Function).order_by(Function.name)
    functions = list((await db.execute(stmt)).scalars().all())
    return [FunctionCompactRead(id=f.id, name=f.name) for f in functions]


@router.get("/options/species", response_model=list[SpeciesCompactRead])
async def list_species_options(
    current_user: UserDep,
    db: DbDep,
) -> list[SpeciesCompactRead]:
    """List all species for selection menus.

    Args:
        current_user: Ensures the caller is authenticated.
        db: Async SQLAlchemy session.

    Returns:
        List of compact species objects.
    """

    _ = current_user
    stmt = select(Species).options(selectinload(Species.family)).order_by(Species.name)
    species = list((await db.execute(stmt)).scalars().all())
    return [SpeciesCompactRead.model_validate(s) for s in species]


def _build_sql_sort_exprs(
    sort_by: str | None,
    sort_dir: str,
    dedup_subq,
    feature_daily_planning: bool,
) -> list:
    """Return a list of SQLAlchemy ORDER BY expressions for the visit dedup subquery."""
    from sqlalchemy import Integer

    is_asc = sort_dir == "asc"
    dir_fn = asc if is_asc else desc

    def nl(expr):
        """Direction with nulls last."""
        return dir_fn(expr).nullslast()

    c = dedup_subq.c

    secondary = [
        asc(func.coalesce(c.s_from_date, date(9999, 12, 31))),
        asc(func.coalesce(c.s_project_code, "")),
        asc(func.coalesce(c.s_cluster_number, "")),
        asc(func.coalesce(c.s_visit_nr, 9999)),
    ]

    if sort_by == "project_code":
        return [nl(c.s_project_code)] + secondary
    if sort_by == "project_location":
        loc_expr = func.coalesce(c.s_cluster_location, c.s_project_location, "")
        return [nl(loc_expr)] + secondary
    if sort_by == "cluster_number":
        return [nl(c.s_cluster_number)] + secondary
    if sort_by == "visit_nr":
        return [nl(c.s_visit_nr)] + secondary
    if sort_by == "period":
        return [nl(c.s_from_date)] + secondary
    if sort_by == "part_of_day":
        return [nl(c.s_part_of_day)] + secondary
    if sort_by == "functions":
        return [nl(func.coalesce(c.s_function_name, ""))] + secondary
    if sort_by == "species":
        return [nl(func.coalesce(c.s_species_name, ""))] + secondary
    if sort_by == "researchers":
        return [nl(func.coalesce(c.s_researcher_name, ""))] + secondary
    if sort_by == "week":
        week_expr = func.coalesce(c.s_planned_week, c.s_provisional_week, 9999)
        return [dir_fn(week_expr)] + secondary
    if sort_by == "date":
        if feature_daily_planning:
            ref_year = func.cast(
                func.coalesce(
                    func.extract("isoyear", c.s_from_date),
                    func.extract("year", func.current_date()),
                ),
                Integer,
            )
            week_as_date = func.to_date(
                func.concat(ref_year, " ", c.s_provisional_week, " 5"),
                literal("IYYY IW ID"),
            )
            unified_date = case(
                (c.s_planned_date.is_not(None), c.s_planned_date),
                (c.s_provisional_week.is_not(None), week_as_date),
                else_=date(9999, 12, 31),
            )
            # planned_date wins over provisional_week within the same week (always ASC tiebreaker)
            date_priority = case(
                (c.s_planned_date.is_not(None), 0),
                else_=1,
            )
            return [dir_fn(unified_date), asc(date_priority)] + secondary
        else:
            week_expr = func.coalesce(c.s_planned_week, c.s_provisional_week, 9999)
            return [dir_fn(week_expr)] + secondary

    # Default sort (no sort_by)
    order_from = func.coalesce(c.s_from_date, date(9999, 12, 31))
    if feature_daily_planning:
        return [
            asc(order_from),
            asc(func.coalesce(c.s_planned_date, date(9999, 12, 31))),
            asc(func.coalesce(c.s_provisional_week, 9999)),
            asc(c.s_project_code),
            asc(c.s_cluster_number),
            asc(c.s_visit_nr),
        ]
    return [
        asc(order_from),
        asc(func.coalesce(c.s_planned_week, c.s_provisional_week, 9999)),
        asc(c.s_project_code),
        asc(c.s_cluster_number),
        asc(c.s_visit_nr),
    ]


_STATUS_ORDER: dict[str, int] = {
    "created": 0,
    "open": 1,
    "planned": 2,
    "overdue": 3,
    "missed": 4,
    "executed": 5,
    "executed_with_deviation": 6,
    "not_executed": 7,
    "needs_action": 8,
    "provisional": 9,
    "approved": 10,
    "rejected": 11,
    "cancelled": 12,
}


def _build_python_sort_key(
    sort_by: str | None,
    sort_dir: str,
    feature_daily_planning: bool,
    status_map: dict | None = None,
):
    """Return (key_fn, reverse) for sorting a list of Visit objects in Python."""
    reverse = sort_dir == "desc"

    def key(v: Visit) -> tuple:
        cluster = v.cluster
        project = getattr(cluster, "project", None)
        ref_year = v.from_date.year if v.from_date else date.today().year

        from_date_val = v.from_date or date.max
        project_code_val = (project.code if project else None) or ""
        cluster_num_val = (cluster.cluster_number if cluster else None) or ""
        visit_nr_val = v.visit_nr if v.visit_nr is not None else 9999
        part_of_day_val = v.part_of_day or ""
        project_location_val = (
            (cluster.location if cluster and cluster.location else None)
            or (project.location if project else None)
            or ""
        )

        if feature_daily_planning:
            planned_val: date = (
                v.planned_date
                or (_isoweek_to_friday(ref_year, v.provisional_week) if v.provisional_week else None)
                or date.max
            )
            date_flag = 0 if v.planned_date else 1
        else:
            week_val = v.planned_week or v.provisional_week or 9999

        sec = (from_date_val, project_code_val, cluster_num_val, visit_nr_val)

        if sort_by == "project_code":
            return (project_code_val, cluster_num_val, visit_nr_val)
        if sort_by == "project_location":
            return (project_location_val, project_code_val, cluster_num_val)
        if sort_by == "cluster_number":
            return (cluster_num_val, project_code_val, visit_nr_val)
        if sort_by == "visit_nr":
            return (visit_nr_val, from_date_val, project_code_val)
        if sort_by == "period":
            return (from_date_val,) + sec[1:]
        if sort_by == "part_of_day":
            return (part_of_day_val, from_date_val, project_code_val)
        if sort_by == "status":
            status_code = (status_map or {}).get(v.id, "created")
            return (_STATUS_ORDER.get(str(status_code), 99), from_date_val, project_code_val)
        if sort_by == "functions":
            fn_val = next((f.name for f in v.functions), v.custom_function_name or "")
            return (fn_val or "", from_date_val, project_code_val)
        if sort_by == "species":
            sp_val = next(
                (s.abbreviation or s.name for s in v.species), v.custom_species_name or ""
            )
            return (sp_val or "", from_date_val, project_code_val)
        if sort_by == "researchers":
            r_val = next((r.full_name or "" for r in v.researchers), "")
            return (r_val, from_date_val, project_code_val)
        if sort_by in ("week", "date"):
            if feature_daily_planning:
                return (planned_val, date_flag, from_date_val, project_code_val)
            return (week_val, from_date_val, project_code_val)

        # Default
        if feature_daily_planning:
            return (from_date_val, planned_val, date_flag, project_code_val, cluster_num_val, visit_nr_val)
        return (from_date_val, week_val, project_code_val, cluster_num_val, visit_nr_val)

    return key, reverse


@router.get("", response_model=VisitListResponse)
async def list_visits(
    current_user: UserDep,
    db: DbDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 100,
    search: Annotated[str | None, Query()] = None,
    statuses: Annotated[list[VisitStatusCode] | None, Query()] = None,
    week: Annotated[int | None, Query(ge=1, le=53)] = None,
    cluster_number: Annotated[str | None, Query()] = None,
    function_ids: Annotated[list[int] | None, Query()] = None,
    species_ids: Annotated[list[int] | None, Query()] = None,
    simulated_today: Annotated[date | None, Query()] = None,
    unplanned_only: Annotated[bool, Query()] = False,
    include_archived: Annotated[bool, Query()] = False,
    only_archived: Annotated[bool, Query()] = False,
    sort_by: Annotated[str | None, Query()] = None,
    sort_dir: Annotated[str, Query()] = "asc",
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
        week: Optional ISO week number to filter by.
        unplanned_only: When true, only visits without provisional/planned weeks are returned.

    Returns:
        Paginated :class:`VisitListResponse` with flattened rows.
    """
    from app.services.visit_query_service import (
        apply_visit_filters,
        get_visit_loading_stmt,
        get_visit_selection_stmt,
    )

    settings = get_settings()
    effective_today: date | None = None
    if settings.test_mode_enabled and getattr(current_user, "admin", False):
        effective_today = simulated_today

    stmt = get_visit_selection_stmt()
    stmt = apply_visit_filters(
        stmt,
        search=search,
        week=week,
        daily_planning=settings.feature_daily_planning,
        cluster_number=cluster_number,
        function_ids=function_ids,
        species_ids=species_ids,
        unplanned_only=unplanned_only,
    )

    if include_archived and only_archived:
        stmt = stmt.where(Visit.is_archived.is_(True))
    elif not include_archived and hasattr(Visit, "is_archived"):
        stmt = stmt.where(Visit.is_archived.is_(False))

    # Add sort columns to the select so they're available after deduplication
    stmt = stmt.add_columns(
        Visit.from_date.label("s_from_date"),
        Visit.planned_date.label("s_planned_date"),
        Visit.planned_week.label("s_planned_week"),
        Visit.provisional_week.label("s_provisional_week"),
        Project.code.label("s_project_code"),
        Project.location.label("s_project_location"),
        Cluster.cluster_number.label("s_cluster_number"),
        Cluster.location.label("s_cluster_location"),
        Visit.visit_nr.label("s_visit_nr"),
        Visit.part_of_day.label("s_part_of_day"),
        func.coalesce(
            select(func.min(Function.name))
            .select_from(visit_functions)
            .join(Function, Function.id == visit_functions.c.function_id)
            .where(visit_functions.c.visit_id == Visit.id)
            .correlate(Visit)
            .scalar_subquery(),
            Visit.custom_function_name,
        ).label("s_function_name"),
        func.coalesce(
            select(func.min(func.coalesce(Species.abbreviation, Species.name)))
            .select_from(visit_species)
            .join(Species, Species.id == visit_species.c.species_id)
            .where(visit_species.c.visit_id == Visit.id)
            .correlate(Visit)
            .scalar_subquery(),
            Visit.custom_species_name,
        ).label("s_species_name"),
        select(func.min(User.full_name))
        .select_from(visit_researchers)
        .join(User, User.id == visit_researchers.c.user_id)
        .where(visit_researchers.c.visit_id == Visit.id)
        .correlate(Visit)
        .scalar_subquery()
        .label("s_researcher_name"),
    )
    # DISTINCT ON (visits.id) requires ORDER BY to start with visits.id
    dedup_subq = stmt.distinct(Visit.id).order_by(Visit.id).subquery()

    sort_exprs = _build_sql_sort_exprs(sort_by, sort_dir, dedup_subq, settings.feature_daily_planning)
    id_stmt = select(dedup_subq.c.id).order_by(*sort_exprs)

    if statuses:
        visit_ids = (await db.execute(id_stmt)).scalars().all()
        total = len(visit_ids)
    else:
        count_stmt = select(func.count()).select_from(id_stmt.subquery())
        total = int((await db.execute(count_stmt)).scalar_one())
        visit_ids = (
            (await db.execute(id_stmt.offset((page - 1) * page_size).limit(page_size)))
            .scalars()
            .all()
        )

    if not visit_ids:
        return VisitListResponse(items=[], total=total, page=page, page_size=page_size)

    stmt_visits = get_visit_loading_stmt(visit_ids, include_archived=include_archived)
    visits = (await db.execute(stmt_visits)).scalars().all()

    # Derive lifecycle status for each visit once, then filter by status
    status_map = await resolve_visit_statuses(db, visits, today=effective_today)

    if statuses:
        allowed = set(statuses)
        visits = [v for v in visits if status_map.get(v.id) in allowed]

    _py_key, _py_reverse = _build_python_sort_key(sort_by, sort_dir, settings.feature_daily_planning, status_map)
    visits.sort(key=_py_key, reverse=_py_reverse)

    if statuses:
        total = len(visits)
        start = (page - 1) * page_size
        end = start + page_size
        page_items = visits[start:end]
    else:
        page_items = visits

    enable_visit_code = settings.enable_visit_code
    items = []
    for v in page_items:
        cluster = v.cluster
        project = getattr(cluster, "project", None)
        project_code = project.code if project else ""
        project_location = (
            (cluster.location if cluster and cluster.location else None)
            or (project.location if project else "")
            or ""
        )
        status = status_map.get(v.id, VisitStatusCode.CREATED)

        items.append(
            {
                "id": v.id,
                "project_id": project.id if project else 0,
                "project_code": project_code,
                "project_location": project_location,
                "project_customer": project.customer if project else None,
                "project_google_drive_folder": (
                    project.google_drive_folder if project else None
                ),
                "cluster_id": cluster.id if cluster else 0,
                "cluster_number": cluster.cluster_number if cluster else "",
                "cluster_address": cluster.address if cluster else "",
                "status": status,
                "function_ids": [f.id for f in v.functions],
                "species_ids": [s.id for s in v.species],
                "functions": [
                    FunctionCompactRead(id=f.id, name=f.name) for f in v.functions
                ],
                "species": [SpeciesCompactRead.model_validate(s) for s in v.species],
                "custom_function_name": v.custom_function_name,
                "custom_species_name": v.custom_species_name,
                "required_researchers": v.required_researchers,
                "visit_nr": v.visit_nr,
                "planned_week": v.planned_week,
                "planned_date": v.planned_date,
                "from_date": v.from_date,
                "to_date": v.to_date,
                "duration": v.duration,
                "min_temperature_celsius": v.min_temperature_celsius,
                "max_wind_force_bft": v.max_wind_force_bft,
                "max_precipitation": v.max_precipitation,
                "expertise_level": v.expertise_level,
                "wbc": v.wbc,
                "fiets": v.fiets,
                "vog": v.vog,
                "hub": v.hub,
                "dvp": v.dvp,
                "sleutel": v.sleutel,
                "remarks_planning": v.remarks_planning,
                "remarks_field": v.remarks_field,
                "priority": v.priority,
                "part_of_day": v.part_of_day,
                "start_time_text": v.start_time_text,
                "planning_locked": v.planning_locked,
                "researchers_locked": v.researchers_locked,
                "researchers": [
                    UserNameRead(id=r.id, full_name=r.full_name) for r in v.researchers
                ],
                "advertized": v.advertized,
                "quote": v.quote,
                "provisional_week": v.provisional_week,
                "provisional_locked": v.provisional_locked,
                "visit_code": compute_visit_code(v) if enable_visit_code else None,
            }
        )

    return VisitListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/export", response_class=Response)
async def export_visits(
    current_user: UserDep,
    db: DbDep,
    search: Annotated[str | None, Query()] = None,
    statuses: Annotated[list[VisitStatusCode] | None, Query()] = None,
    week: Annotated[int | None, Query(ge=1, le=53)] = None,
    cluster_number: Annotated[str | None, Query()] = None,
    function_ids: Annotated[list[int] | None, Query()] = None,
    species_ids: Annotated[list[int] | None, Query()] = None,
    simulated_today: Annotated[date | None, Query()] = None,
    unplanned_only: Annotated[bool, Query()] = False,
    include_archived: Annotated[bool, Query()] = False,
    only_archived: Annotated[bool, Query()] = False,
    sort_by: Annotated[str | None, Query()] = None,
    sort_dir: Annotated[str, Query()] = "asc",
) -> Response:
    """Export filtered visits to CSV."""
    import csv
    import io
    from fastapi.responses import StreamingResponse

    from app.services.visit_query_service import (
        apply_visit_filters,
        get_visit_loading_stmt,
        get_visit_selection_stmt,
    )

    settings = get_settings()
    effective_today: date | None = None
    if settings.test_mode_enabled and getattr(current_user, "admin", False):
        effective_today = simulated_today

    stmt = get_visit_selection_stmt()
    stmt = apply_visit_filters(
        stmt,
        search=search,
        week=week,
        daily_planning=settings.feature_daily_planning,
        cluster_number=cluster_number,
        function_ids=function_ids,
        species_ids=species_ids,
        unplanned_only=unplanned_only,
    )

    if include_archived and only_archived:
        stmt = stmt.where(Visit.is_archived.is_(True))
    elif not include_archived and hasattr(Visit, "is_archived"):
        stmt = stmt.where(Visit.is_archived.is_(False))

    # Add sort columns to the select so they're available after deduplication
    stmt = stmt.add_columns(
        Visit.from_date.label("s_from_date"),
        Visit.planned_date.label("s_planned_date"),
        Visit.planned_week.label("s_planned_week"),
        Visit.provisional_week.label("s_provisional_week"),
        Project.code.label("s_project_code"),
        Project.location.label("s_project_location"),
        Cluster.cluster_number.label("s_cluster_number"),
        Cluster.location.label("s_cluster_location"),
        Visit.visit_nr.label("s_visit_nr"),
        Visit.part_of_day.label("s_part_of_day"),
        func.coalesce(
            select(func.min(Function.name))
            .select_from(visit_functions)
            .join(Function, Function.id == visit_functions.c.function_id)
            .where(visit_functions.c.visit_id == Visit.id)
            .correlate(Visit)
            .scalar_subquery(),
            Visit.custom_function_name,
        ).label("s_function_name"),
        func.coalesce(
            select(func.min(func.coalesce(Species.abbreviation, Species.name)))
            .select_from(visit_species)
            .join(Species, Species.id == visit_species.c.species_id)
            .where(visit_species.c.visit_id == Visit.id)
            .correlate(Visit)
            .scalar_subquery(),
            Visit.custom_species_name,
        ).label("s_species_name"),
        select(func.min(User.full_name))
        .select_from(visit_researchers)
        .join(User, User.id == visit_researchers.c.user_id)
        .where(visit_researchers.c.visit_id == Visit.id)
        .correlate(Visit)
        .scalar_subquery()
        .label("s_researcher_name"),
    )
    # DISTINCT ON (visits.id) requires ORDER BY to start with visits.id
    dedup_subq = stmt.distinct(Visit.id).order_by(Visit.id).subquery()

    sort_exprs = _build_sql_sort_exprs(sort_by, sort_dir, dedup_subq, settings.feature_daily_planning)
    id_stmt = select(dedup_subq.c.id).order_by(*sort_exprs)
    visit_ids = (await db.execute(id_stmt)).scalars().all()

    if not visit_ids:
        # Return empty csv
        stream = io.StringIO()
        csv.writer(stream).writerow(["Geen resultaten"])
        stream.seek(0)
        return StreamingResponse(
            stream,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=bezoeken.csv"},
        )

    stmt_visits = get_visit_loading_stmt(visit_ids, include_archived=include_archived)
    visits = (await db.execute(stmt_visits)).scalars().all()
    status_map = await resolve_visit_statuses(db, visits, today=effective_today)

    if statuses:
        allowed = set(statuses)
        visits = [v for v in visits if status_map.get(v.id) in allowed]

    _py_key, _py_reverse = _build_python_sort_key(sort_by, sort_dir, settings.feature_daily_planning, status_map)
    visits.sort(key=_py_key, reverse=_py_reverse)

    def iter_csv():
        output = io.StringIO()
        writer = csv.writer(output)

        base_headers = [
            "Projectcode",
            "Locatie",
            "Cluster",
            "Bezoek nr",
            "Status",
            "Week/Datum",
            "Functies",
            "Soorten",
            "Periode",
            "Dagdeel",
            "Onderzoekers",
        ]
        extra_headers = [
            "Klant",
            "Adres",
            "Starttijd",
            "Duur (uur)",
            "Min temp (°C)",
            "Max wind (Bft)",
            "Max neerslag",
            "Expertise niveau",
            "WBC",
            "Fiets",
            "VOG",
            "HUB",
            "DVP",
            "Sleutel",
            "Prioriteit",
            "Opmerkingen veld",
            "Opmerkingen planning",
        ] if settings.full_csv_export else []
        writer.writerow(base_headers + extra_headers)
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        for v in visits:
            cluster = v.cluster
            project = getattr(cluster, "project", None)
            project_code = project.code if project else ""
            project_location = (
                (cluster.location if cluster and cluster.location else None)
                or (project.location if project else "")
                or ""
            )
            status = status_map.get(v.id, VisitStatusCode.CREATED)

            date_str = ""
            if v.planned_date:
                date_str = v.planned_date.strftime("%d-%m-%Y")
            elif v.planned_week:
                date_str = f"Week {v.planned_week}"
            elif v.provisional_week:
                date_str = f"Week {v.provisional_week} (voorlopig)"

            functions_str = ", ".join([f.name for f in v.functions])
            if v.custom_function_name:
                functions_str = v.custom_function_name

            species_str = ", ".join([s.abbreviation or s.name for s in v.species])
            if v.custom_species_name:
                species_str = v.custom_species_name

            period_str = ""
            if v.from_date and v.to_date:
                period_str = (
                    f"{v.from_date.strftime('%d-%m')} / {v.to_date.strftime('%d-%m')}"
                )

            researchers_str = ", ".join(
                [r.full_name or f"User {r.id}" for r in v.researchers]
            )

            row = [
                project_code,
                project_location,
                cluster.cluster_number if cluster else "",
                v.visit_nr or "",
                status,
                date_str,
                functions_str,
                species_str,
                period_str,
                v.part_of_day or "",
                researchers_str,
            ]

            if settings.full_csv_export:
                duration_hours = (
                    round(v.duration / 60, 2) if v.duration is not None else ""
                )
                row += [
                    project.customer if project and getattr(project, "customer", None) else "",
                    cluster.address if cluster and getattr(cluster, "address", None) else "",
                    v.start_time_text or "",
                    duration_hours,
                    v.min_temperature_celsius if v.min_temperature_celsius is not None else "",
                    v.max_wind_force_bft if v.max_wind_force_bft is not None else "",
                    v.max_precipitation or "",
                    v.expertise_level or "",
                    "Ja" if v.wbc else "Nee",
                    "Ja" if v.fiets else "Nee",
                    "Ja" if v.vog else "Nee",
                    "Ja" if v.hub else "Nee",
                    "Ja" if v.dvp else "Nee",
                    "Ja" if v.sleutel else "Nee",
                    "Ja" if v.priority else "Nee",
                    v.remarks_field or "",
                    v.remarks_planning or "",
                ]

            writer.writerow(row)
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

    return StreamingResponse(
        iter_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=bezoeken.csv"},
    )


@router.get("/ical", response_class=Response)
async def download_week_ical(
    current_user: UserDep,
    db: DbDep,
    week: Annotated[int, Query()],
    year: Annotated[int | None, Query()] = None,
) -> Response:
    """Download an iCal file for the current user's visits in the given week."""
    settings = get_settings()
    if not settings.enable_ical:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    effective_year = year if year is not None else date.today().year
    week_start = date.fromisocalendar(effective_year, week, 1)
    week_end = week_start + timedelta(days=6)

    stmt = (
        select_active(Visit)
        .where(Visit.researchers.any(User.id == current_user.id))
        .options(
            selectinload(Visit.researchers),
            selectinload(Visit.functions),
            selectinload(Visit.species),
            selectinload(Visit.cluster).selectinload(Cluster.project),
        )
        .where(
            and_(
                Visit.planned_week == week,
                or_(
                    Visit.from_date.is_(None),
                    extract("year", Visit.from_date) == effective_year,
                ),
            )
            | and_(
                Visit.planned_date >= week_start,
                Visit.planned_date <= week_end,
            )
        )
    )

    visits = (await db.execute(stmt)).scalars().unique().all()

    from app.services.ical_service import build_week_ical

    ics_bytes = build_week_ical(list(visits), week, effective_year)
    return Response(
        content=ics_bytes,
        media_type="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="planning-week-{week}.ics"'},
    )


@router.get("/{visit_id}/ical", response_class=Response)
async def download_visit_ical(
    current_user: UserDep,
    db: DbDep,
    visit_id: int,
) -> Response:
    """Download an iCal file for a single visit."""
    settings = get_settings()
    if not settings.enable_ical:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    stmt = (
        select_active(Visit)
        .where(Visit.id == visit_id)
        .options(
            selectinload(Visit.researchers),
            selectinload(Visit.functions),
            selectinload(Visit.species),
            selectinload(Visit.cluster).selectinload(Cluster.project),
        )
    )

    visit = (await db.execute(stmt)).scalars().first()
    if visit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    from app.services.ical_service import build_visit_ical

    ics_bytes = build_visit_ical(visit)
    return Response(
        content=ics_bytes,
        media_type="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="bezoek-{visit_id}.ics"'},
    )


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
        select_active(Visit)
        .where(Visit.id == visit_id)
        .options(
            selectinload(Visit.cluster).selectinload(Cluster.project),
            selectinload(Visit.functions),
            selectinload(Visit.species).selectinload(Species.family),
            selectinload(Visit.researchers),
            selectinload(Visit.protocol_visit_windows).selectinload(
                ProtocolVisitWindow.protocol
            ),
        )
    )
    visit = (await db.execute(stmt)).scalars().first()
    if visit is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Visit not found"
        )

    visit_status = await resolve_visit_status(db, visit, today=effective_today)
    cluster = visit.cluster
    project: Project | None = getattr(cluster, "project", None)
    project_code = project.code if project else ""
    project_location = (
        (cluster.location if cluster and cluster.location else None)
        or (project.location if project else "")
        or ""
    )
    project_customer = project.customer if project else None
    project_google_drive_folder = project.google_drive_folder if project else None

    return VisitListRow(
        id=visit.id,
        project_id=project.id if project else 0,
        project_code=project_code,
        project_location=project_location,
        project_customer=project_customer,
        project_google_drive_folder=project_google_drive_folder,
        cluster_id=cluster.id if cluster else 0,
        cluster_number=cluster.cluster_number if cluster else "",
        cluster_address=cluster.address if cluster else "",
        status=visit_status,
        function_ids=[f.id for f in visit.functions],
        species_ids=[s.id for s in visit.species],
        functions=[FunctionCompactRead(id=f.id, name=f.name) for f in visit.functions],
        species=[SpeciesCompactRead.model_validate(s) for s in visit.species],
        custom_function_name=visit.custom_function_name,
        custom_species_name=visit.custom_species_name,
        required_researchers=visit.required_researchers,
        visit_nr=visit.visit_nr,
        planned_week=visit.planned_week,
        planned_date=visit.planned_date,
        from_date=visit.from_date,
        to_date=visit.to_date,
        duration=visit.duration,
        min_temperature_celsius=visit.min_temperature_celsius,
        max_wind_force_bft=visit.max_wind_force_bft,
        max_precipitation=visit.max_precipitation,
        expertise_level=visit.expertise_level,
        wbc=visit.wbc,
        fiets=visit.fiets,
        vog=visit.vog,
        hub=visit.hub,
        dvp=visit.dvp,
        sleutel=visit.sleutel,
        remarks_planning=visit.remarks_planning,
        remarks_field=visit.remarks_field,
        priority=visit.priority,
        part_of_day=visit.part_of_day,
        start_time_text=visit.start_time_text,
        planning_locked=visit.planning_locked,
        researchers_locked=visit.researchers_locked,
        researchers=[
            UserNameRead(id=r.id, full_name=r.full_name) for r in visit.researchers
        ],
        advertized=visit.advertized,
        quote=visit.quote,
        provisional_week=visit.provisional_week,
        provisional_locked=visit.provisional_locked,
        visit_code=compute_visit_code(visit) if settings.enable_visit_code else None,
    )


@router.post("", response_model=VisitRead)
async def create_visit(
    admin: AdminDep,
    db: DbDep,
    payload: VisitCreate,
) -> Visit:
    """Create a new visit with provided fields."""

    _validate_planning_locked_payload(
        planning_locked=payload.planning_locked,
        planned_week=payload.planned_week,
        planned_date=payload.planned_date,
        researcher_ids=payload.researcher_ids,
    )
    await _validate_researchers_locked_payload(
        db,
        researchers_locked=getattr(payload, "researchers_locked", False),
        researcher_ids=payload.researcher_ids,
    )

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

    await sync_cluster_pvw_links(db, visit.cluster_id)
    await db.commit()

    # Re-fetch with eager loading to avoid lazy-load (MissingGreenlet) in response
    stmt = (
        select_active(Visit)
        .where(Visit.id == visit.id)
        .options(
            selectinload(Visit.functions),
            selectinload(Visit.species).selectinload(Species.family),
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
        select_active(Visit)
        .where(Visit.advertized.is_(True))
        .options(
            selectinload(Visit.cluster).selectinload(Cluster.project),
            selectinload(Visit.functions),
            selectinload(Visit.species).selectinload(Species.family),
            selectinload(Visit.researchers),
            selectinload(Visit.protocol_visit_windows).selectinload(
                ProtocolVisitWindow.protocol
            ),
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
        project_location = (
            (cluster.location if cluster and cluster.location else None)
            or (project.location if project else "")
            or ""
        )
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
                project_id=project.id if project else 0,
                project_code=project_code,
                project_location=project_location,
                project_customer=project.customer if project else None,
                project_google_drive_folder=(
                    project.google_drive_folder if project else None
                ),
                cluster_id=cluster.id if cluster else 0,
                cluster_number=cluster.cluster_number if cluster else "",
                cluster_address=cluster.address if cluster else "",
                status=status,
                function_ids=[f.id for f in v.functions],
                species_ids=[s.id for s in v.species],
                functions=[
                    FunctionCompactRead(id=f.id, name=f.name) for f in v.functions
                ],
                species=[SpeciesCompactRead.model_validate(s) for s in v.species],
                custom_function_name=v.custom_function_name,
                custom_species_name=v.custom_species_name,
                required_researchers=v.required_researchers,
                visit_nr=v.visit_nr,
                planned_week=v.planned_week,
                planned_date=v.planned_date,
                from_date=v.from_date,
                to_date=v.to_date,
                duration=v.duration,
                min_temperature_celsius=v.min_temperature_celsius,
                max_wind_force_bft=v.max_wind_force_bft,
                max_precipitation=v.max_precipitation,
                expertise_level=v.expertise_level,
                wbc=v.wbc,
                fiets=v.fiets,
                vog=v.vog,
                hub=v.hub,
                dvp=v.dvp,
                sleutel=v.sleutel,
                remarks_planning=v.remarks_planning,
                remarks_field=v.remarks_field,
                priority=v.priority,
                part_of_day=v.part_of_day,
                start_time_text=v.start_time_text,
                planning_locked=v.planning_locked,
                researchers=[
                    UserNameRead(id=r.id, full_name=r.full_name) for r in v.researchers
                ],
                advertized=v.advertized,
                quote=v.quote,
                advertized_by=advertised_by,
                can_accept=can_accept,
                visit_code=compute_visit_code(v)
                if settings.enable_visit_code
                else None,
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
        .options(selectinload(ActivityLog.actor), selectinload(ActivityLog.actors))
        .order_by(ActivityLog.created_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{visit_id}/researcher-qualification")
async def check_researcher_qualification(
    _: AdminDep,
    db: DbDep,
    visit_id: int,
    researcher_ids: Annotated[list[int], Query()] = [],
) -> dict:
    """Check whether the given researchers are qualified for the visit.

    Returns a list of unqualified researcher names so the frontend can warn the user.
    """
    stmt = (
        select_active(Visit)
        .where(Visit.id == visit_id)
        .options(
            selectinload(Visit.functions),
            selectinload(Visit.species).selectinload(Species.family),
        )
    )
    visit = (await db.execute(stmt)).scalars().first()
    if visit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Visit not found")

    if not researcher_ids:
        return {"unqualified": []}

    user_stmt = select(User).where(
        User.id.in_(researcher_ids),
        User.deleted_at.is_(None),
    )
    users = (await db.execute(user_stmt)).scalars().all()

    unqualified = [
        {"id": u.id, "full_name": u.full_name}
        for u in users
        if not _qualifies_user_for_visit(u, visit)
    ]
    return {"unqualified": unqualified}


@router.put("/{visit_id}", response_model=VisitRead)
async def update_visit(
    admin: AdminDep, db: DbDep, visit_id: int, payload: VisitUpdate
) -> Visit:
    """Update a visit with provided fields.

    For now we accept the VisitRead payload to keep implementation minimal; in a
    follow-up we can tighten this to a dedicated VisitUpdate schema.
    """

    stmt = (
        select(Visit)
        .where(Visit.id == visit_id)
        .options(
            selectinload(Visit.cluster).selectinload(Cluster.project),
            selectinload(Visit.species).selectinload(Species.family),
            selectinload(Visit.functions),
            selectinload(Visit.researchers),
        )
    )
    visit = (await db.execute(stmt)).scalars().first()
    if visit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    old_advertized = bool(getattr(visit, "advertized", False))

    # Map simple scalar fields based on explicitly provided payload keys.
    # This allows the client to clear nullable columns by sending null,
    # while leaving omitted fields untouched.
    data = payload.dict(
        exclude_unset=True,
        exclude={"function_ids", "species_ids", "researcher_ids", "cluster_id"},
    )

    # Handle cluster_id change if provided
    if payload.cluster_id is not None:
        new_cluster = await db.get(Cluster, payload.cluster_id)
        if new_cluster is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cluster not found",
            )
        visit.cluster_id = payload.cluster_id

    # Consistency check: If planned_week is cleared (set to None), also clear planned_date
    if "planned_week" in data and data["planned_week"] is None:
        if "planned_date" not in data:
            data["planned_date"] = None

    # Consistency check: If planned_date is set without a planned_week, derive the
    # ISO week number from the date so the planning board filters work.
    if "planned_date" in data and data["planned_date"] is not None:
        if data.get("planned_week") is None:
            data["planned_week"] = data["planned_date"].isocalendar().week

    advertized_update = data.pop("advertized", None)

    for field, value in data.items():
        setattr(visit, field, value)

    if advertized_update is not None:
        visit.advertized = advertized_update

    new_advertized = bool(getattr(visit, "advertized", False))
    if advertized_update is not None and new_advertized != old_advertized:
        action = "visit_advertised" if new_advertized else "visit_advertised_cancelled"
        cluster = visit.cluster
        project: Project | None = getattr(cluster, "project", None)
        await log_activity(
            db,
            actor_id=admin.id,
            action=action,
            target_type="visit",
            target_id=visit.id,
            details={
                "project_code": project.code if project else None,
                "cluster_number": cluster.cluster_number if cluster else None,
                "visit_nr": visit.visit_nr,
            },
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

    final_planning_locked = bool(getattr(visit, "planning_locked", False))
    final_planned_week = getattr(visit, "planned_week", None)
    final_planned_date = getattr(visit, "planned_date", None)
    final_researcher_ids = payload.researcher_ids
    if final_researcher_ids is None:
        final_researcher_ids = [r.id for r in (visit.researchers or [])]
    _validate_planning_locked_payload(
        planning_locked=final_planning_locked,
        planned_week=final_planned_week,
        planned_date=final_planned_date,
        researcher_ids=final_researcher_ids,
    )
    final_researchers_locked = bool(getattr(visit, "researchers_locked", False))
    await _validate_researchers_locked_payload(
        db,
        researchers_locked=final_researchers_locked,
        researcher_ids=final_researcher_ids,
        visit=visit,
    )

    # Re-sync cluster PVW links so the whole cluster stays consistent when
    # species, functions or visit_nr change.
    is_visit_nr_changed = "visit_nr" in data
    if (
        payload.function_ids is not None
        or payload.species_ids is not None
        or is_visit_nr_changed
    ):
        await sync_cluster_pvw_links(db, visit.cluster_id)

    await db.commit()
    # Re-fetch with eager loading to avoid lazy-load (MissingGreenlet) in response
    stmt = (
        select_active(Visit)
        .where(Visit.id == visit.id)
        .options(
            selectinload(Visit.functions),
            selectinload(Visit.species).selectinload(Species.family),
            selectinload(Visit.researchers),
        )
    )
    visit_loaded = (await db.execute(stmt)).scalars().first()
    return visit_loaded or visit


async def _get_visit_for_status_change(db: AsyncSession, visit_id: int) -> Visit:
    stmt = (
        select(Visit)
        .where(Visit.id == visit_id)
        .options(
            selectinload(Visit.researchers),
            selectinload(Visit.cluster).selectinload(Cluster.project),
        )
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

    cluster = visit.cluster
    project: Project | None = getattr(cluster, "project", None)

    researcher_ids = [r.id for r in visit.researchers] if visit.researchers else []
    log_details: dict = {
        "execution_date": payload.execution_date.isoformat(),
        "comment": payload.comment,
        "project_code": project.code if project else None,
        "cluster_number": cluster.cluster_number if cluster else None,
        "visit_nr": visit.visit_nr,
    }

    if user.admin and researcher_ids:
        log_details["admin_id"] = user.id
        await log_activity(
            db,
            actor_ids=researcher_ids,
            action="visit_executed",
            target_type="visit",
            target_id=visit_id,
            details=log_details,
        )
    else:
        await log_activity(
            db,
            actor_id=user.id,
            action="visit_executed",
            target_type="visit",
            target_id=visit_id,
            details=log_details,
        )

    # Update subsequent visits
    if payload.execution_date:
        await update_subsequent_visits(db, visit, payload.execution_date)

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

    stmt = (
        select(Visit)
        .where(Visit.id == visit_id)
        .options(selectinload(Visit.cluster).selectinload(Cluster.project))
    )
    visit = (await db.execute(stmt)).scalars().first()
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
        visit.planned_date = None
        if visit.planning_locked:
            # planning_locked was set: clear researchers and unset the lock
            await db.execute(
                delete(visit_researchers).where(visit_researchers.c.visit_id == visit.id)
            )
            visit.planning_locked = False
        elif not visit.researchers_locked:
            # No locks active: clear researchers normally
            await db.execute(
                delete(visit_researchers).where(visit_researchers.c.visit_id == visit.id)
            )
        # If researchers_locked (and not planning_locked): keep researchers + researchers_locked
        planned_week = None
        researcher_ids: list[int] | None = None
    else:
        # For planned mode, either planned_date or planned_week must be set,
        # along with researcher_ids.
        if payload.researcher_ids is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="researcher_ids is required when mode is 'planned'",
            )
        if payload.planned_date is None and payload.planned_week is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "planned_date or planned_week is required when mode is 'planned'"
                ),
            )

        # When planned_date is provided without a planned_week, derive the
        # ISO week number from the date so the planning board filters work.
        planned_week = payload.planned_week
        if planned_week is None and payload.planned_date is not None:
            planned_week = payload.planned_date.isocalendar().week
        visit.planned_week = planned_week
        visit.planned_date = payload.planned_date
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
        researcher_ids = list(payload.researcher_ids)

    cluster = visit.cluster
    project: Project | None = getattr(cluster, "project", None)

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
            "project_code": project.code if project else None,
            "cluster_number": cluster.cluster_number if cluster else None,
            "visit_nr": visit.visit_nr,
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
    new_advertized = bool(payload.advertized)

    if new_advertized == old_advertized:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    visit.advertized = new_advertized

    action = "visit_advertised" if new_advertized else "visit_advertised_cancelled"
    cluster = visit.cluster
    project: Project | None = getattr(cluster, "project", None)

    await log_activity(
        db,
        actor_id=user.id,
        action=action,
        target_type="visit",
        target_id=visit.id,
        details={
            "project_code": project.code if project else None,
            "cluster_number": cluster.cluster_number if cluster else None,
            "visit_nr": visit.visit_nr,
        },
        commit=False,
    )

    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/audit/list", response_model=list[VisitListRow])
async def list_visits_for_audit(
    current_user: UserDep,
    db: DbDep,
    simulated_today: Annotated[date | None, Query()] = None,
) -> list[VisitListRow]:
    """Return all visits that are relevant for admin audit.

    When ``AUDIT_OVERVIEW_PUBLIC`` is enabled, all authenticated users may
    access this endpoint (read-only overview). Otherwise restricted to admins.

    Args:
        current_user: Authenticated user; admin required unless audit_overview_public is set.
        db: Async SQLAlchemy session.

    Returns:
        List of :class:`VisitListRow` entries for visits that require or
        have undergone audit.
    """

    settings = get_settings()
    if not settings.audit_overview_public and not current_user.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    effective_today: date | None = None
    if settings.test_mode_enabled:
        effective_today = simulated_today
    stmt = select(Visit).options(
        selectinload(Visit.cluster).selectinload(Cluster.project),
        selectinload(Visit.functions),
        selectinload(Visit.species).selectinload(Species.family),
        selectinload(Visit.researchers),
        selectinload(Visit.protocol_visit_windows).selectinload(
            ProtocolVisitWindow.protocol
        ),
    )
    visits = (await db.execute(stmt)).scalars().all()

    status_map = await resolve_visit_statuses(db, visits, today=effective_today)

    relevant_statuses: set[VisitStatusCode] = {
        VisitStatusCode.EXECUTED,
        VisitStatusCode.EXECUTED_WITH_DEVIATION,
        VisitStatusCode.NEEDS_ACTION,
        VisitStatusCode.PROVISIONAL,
        VisitStatusCode.APPROVED,
        VisitStatusCode.REJECTED,
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
        cluster_number = cluster.cluster_number if cluster else ""
        visit_nr = v.visit_nr or 0
        return (from_date, project_code, cluster_number, visit_nr)

    visits.sort(key=_sort_key)

    items: list[VisitListRow] = []
    for v in visits:
        cluster = v.cluster
        project: Project | None = getattr(cluster, "project", None)
        project_code = project.code if project else ""
        project_location = (
            (cluster.location if cluster and cluster.location else None)
            or (project.location if project else "")
            or ""
        )
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
                project_id=project.id if project else 0,
                project_code=project_code,
                project_location=project_location,
                project_customer=project.customer if project else None,
                project_google_drive_folder=(
                    project.google_drive_folder if project else None
                ),
                cluster_id=cluster.id if cluster else 0,
                cluster_number=cluster.cluster_number if cluster else "",
                cluster_address=cluster.address if cluster else "",
                status=status,
                function_ids=[f.id for f in v.functions],
                species_ids=[s.id for s in v.species],
                functions=[
                    FunctionCompactRead(id=f.id, name=f.name) for f in v.functions
                ],
                species=[SpeciesCompactRead.model_validate(s) for s in v.species],
                custom_function_name=v.custom_function_name,
                custom_species_name=v.custom_species_name,
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
                vog=v.vog,
                hub=v.hub,
                dvp=v.dvp,
                sleutel=v.sleutel,
                remarks_planning=v.remarks_planning,
                remarks_field=v.remarks_field,
                priority=v.priority,
                part_of_day=v.part_of_day,
                start_time_text=v.start_time_text,
                planning_locked=v.planning_locked,
                researchers=[
                    UserNameRead(id=r.id, full_name=r.full_name) for r in v.researchers
                ],
                advertized=v.advertized,
                quote=v.quote,
                visit_code=compute_visit_code(v)
                if settings.enable_visit_code
                else None,
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

    cluster = visit.cluster
    project: Project | None = getattr(cluster, "project", None)

    researcher_ids = [r.id for r in visit.researchers] if visit.researchers else []
    log_details: dict = {
        "execution_date": payload.execution_date.isoformat(),
        "reason": payload.reason,
        "comment": payload.comment,
        "project_code": project.code if project else None,
        "cluster_number": cluster.cluster_number if cluster else None,
        "visit_nr": visit.visit_nr,
    }

    if user.admin and researcher_ids:
        log_details["admin_id"] = user.id
        await log_activity(
            db,
            actor_ids=researcher_ids,
            action="visit_executed_with_deviation",
            target_type="visit",
            target_id=visit_id,
            details=log_details,
        )
    else:
        await log_activity(
            db,
            actor_id=user.id,
            action="visit_executed_with_deviation",
            target_type="visit",
            target_id=visit_id,
            details=log_details,
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

    cluster = visit.cluster
    project: Project | None = getattr(cluster, "project", None)

    await log_activity(
        db,
        actor_id=user.id,
        action="visit_not_executed",
        target_type="visit",
        target_id=visit_id,
        details={
            "date": payload.date.isoformat(),
            "reason": payload.reason,
            "project_code": project.code if project else None,
            "cluster_number": cluster.cluster_number if cluster else None,
            "visit_nr": visit.visit_nr,
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

    stmt = (
        select(Visit)
        .where(Visit.id == visit_id)
        .options(selectinload(Visit.cluster).selectinload(Cluster.project))
    )
    visit = (await db.execute(stmt)).scalars().first()
    if visit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    cluster = visit.cluster
    project: Project | None = getattr(cluster, "project", None)

    await log_activity(
        db,
        actor_id=admin.id,
        action="visit_approved",
        target_type="visit",
        target_id=visit_id,
        details={
            "comment": payload.comment,
            "audit": None if payload.audit is None else payload.audit.model_dump(),
            "project_code": project.code if project else None,
            "cluster_number": cluster.cluster_number if cluster else None,
            "visit_nr": visit.visit_nr,
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

    stmt = (
        select(Visit)
        .where(Visit.id == visit_id)
        .options(selectinload(Visit.cluster).selectinload(Cluster.project))
    )
    visit = (await db.execute(stmt)).scalars().first()
    if visit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    cluster = visit.cluster
    project: Project | None = getattr(cluster, "project", None)

    await log_activity(
        db,
        actor_id=admin.id,
        action="visit_rejected",
        target_type="visit",
        target_id=visit_id,
        details={
            "reason": payload.reason,
            "audit": None if payload.audit is None else payload.audit.model_dump(),
            "project_code": project.code if project else None,
            "cluster_number": cluster.cluster_number if cluster else None,
            "visit_nr": visit.visit_nr,
        },
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{visit_id}/audit", response_model=VisitAuditRead)
async def get_visit_audit(
    _: AdminDep,
    db: DbDep,
    visit_id: int,
) -> VisitAudit:
    """Return the current audit record for a visit, or 404 if none exists yet."""

    stmt = (
        select(VisitAudit)
        .where(VisitAudit.visit_id == visit_id)
        .options(
            selectinload(VisitAudit.created_by),
            selectinload(VisitAudit.updated_by),
        )
    )
    audit = (await db.execute(stmt)).scalars().first()
    if audit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return audit


# ActivityLog action written for each audit status transition.
_AUDIT_LIFECYCLE_ACTION: dict[AuditStatus, str] = {
    AuditStatus.APPROVED: "visit_approved",
    AuditStatus.REJECTED: "visit_rejected",
    AuditStatus.NEEDS_ACTION: "visit_needs_action",
    AuditStatus.PROVISIONAL: "visit_provisional",
}

# Audit statuses that drive the ActivityLog-based lifecycle status (approved /
# rejected).  Changing *away* from these requires a visit_status_cleared entry
# so that derive_visit_status falls back to the execution-based status.
_LIFECYCLE_SETTING_STATUSES: frozenset[AuditStatus] = frozenset(
    {AuditStatus.APPROVED, AuditStatus.REJECTED}
)


@router.put("/{visit_id}/audit", response_model=VisitAuditRead)
async def upsert_visit_audit(
    admin: AdminDep,
    db: DbDep,
    visit_id: int,
    payload: VisitAuditWrite,
) -> VisitAudit:
    """Create or update the audit record for a visit.

    Upserts a single ``VisitAudit`` row (one per visit). When the audit
    status changes to ``approved`` or ``rejected``, the corresponding
    ``visit_approved`` / ``visit_rejected`` action is appended to the
    ``ActivityLog`` so the visit lifecycle status stays consistent with
    existing behaviour. When changing *away* from those statuses a
    ``visit_status_cleared`` entry is written instead.
    """

    # Verify the visit exists.
    visit_stmt = (
        select(Visit)
        .where(Visit.id == visit_id)
        .options(
            selectinload(Visit.cluster).selectinload(Cluster.project),
            selectinload(Visit.researchers),
        )
    )
    visit = (await db.execute(visit_stmt)).scalars().first()
    if visit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    # Load existing audit (if any) to determine previous status.
    audit_stmt = (
        select(VisitAudit)
        .where(VisitAudit.visit_id == visit_id)
        .options(
            selectinload(VisitAudit.created_by),
            selectinload(VisitAudit.updated_by),
        )
    )
    audit = (await db.execute(audit_stmt)).scalars().first()
    previous_status: AuditStatus | None = (
        AuditStatus(audit.status) if audit is not None else None
    )

    # Serialize nested Pydantic models to plain dicts for JSON storage.
    errors_data = [e.model_dump() for e in payload.errors]
    species_data = {k: v.model_dump() for k, v in payload.species_functions.items()}

    if audit is None:
        audit = VisitAudit(
            visit_id=visit_id,
            status=payload.status,
            errors=errors_data,
            species_functions=species_data,
            remarks=payload.remarks,
            remarks_outside_pg=payload.remarks_outside_pg,
            created_by_id=admin.id,
        )
        db.add(audit)
    else:
        audit.status = payload.status
        audit.errors = errors_data
        audit.species_functions = species_data
        audit.remarks = payload.remarks
        audit.remarks_outside_pg = payload.remarks_outside_pg
        audit.updated_by_id = admin.id

    await db.flush()

    # Keep the ActivityLog-based visit lifecycle in sync.
    cluster = visit.cluster
    project: Project | None = getattr(cluster, "project", None)
    lifecycle_details = {
        "project_code": project.code if project else None,
        "cluster_number": cluster.cluster_number if cluster else None,
        "visit_nr": visit.visit_nr,
    }

    new_status = payload.status

    # Check if the visit lifecycle status has drifted away from an expected
    # lifecycle-setting audit status (e.g. APPROVED or REJECTED) because of
    # intermediate actions like a visit re-execution.
    expected_status_code = None
    if new_status == AuditStatus.APPROVED:
        expected_status_code = VisitStatusCode.APPROVED
    elif new_status == AuditStatus.REJECTED:
        expected_status_code = VisitStatusCode.REJECTED

    current_lifecycle_status = await resolve_visit_status(db, visit)
    lifecycle_drifted = (
        expected_status_code is not None
        and current_lifecycle_status != expected_status_code
    )

    if new_status != previous_status or lifecycle_drifted:
        # When changing away from an ActivityLog-driven lifecycle status
        # (approved / rejected) to an audit-driven one, clear the lifecycle
        # entry so derive_visit_status falls back to the execution state.
        if (
            previous_status in _LIFECYCLE_SETTING_STATUSES
            and new_status not in _LIFECYCLE_SETTING_STATUSES
        ):
            await log_activity(
                db,
                actor_id=admin.id,
                action="visit_status_cleared",
                target_type="visit",
                target_id=visit_id,
                details=lifecycle_details,
                commit=False,
            )

        # Log every audit status change for traceability (or if lifecycle drifted).
        await log_activity(
            db,
            actor_id=admin.id,
            action=_AUDIT_LIFECYCLE_ACTION[new_status],
            target_type="visit",
            target_id=visit_id,
            details=lifecycle_details,
            commit=False,
        )

    await db.commit()
    await db.refresh(audit, ["created_by", "updated_by"])
    return audit


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

    stmt = (
        select(Visit)
        .where(Visit.id == visit_id)
        .options(selectinload(Visit.cluster).selectinload(Cluster.project))
    )
    visit = (await db.execute(stmt)).scalars().first()
    if visit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    cluster = visit.cluster
    project: Project | None = getattr(cluster, "project", None)

    await log_activity(
        db,
        actor_id=admin.id,
        action="visit_cancelled",
        target_type="visit",
        target_id=visit_id,
        details={
            "reason": payload.reason,
            "project_code": project.code if project else None,
            "cluster_number": cluster.cluster_number if cluster else None,
            "visit_nr": visit.visit_nr,
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
    cluster_id = visit.cluster_id
    await soft_delete_entity(db, visit, cascade=False)
    await sync_cluster_pvw_links(db, cluster_id)
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
    simulated_today: Annotated[date | None, Query()] = None,
) -> Response:
    """Accept an advertised visit and reassign researchers.

    The current user must qualify for the visit according to the same rules used
    by the planner. When accepted, the user is added as a researcher (if not
    already present), the original advertiser is removed when known and the
    advertised flag is cleared. Corresponding activity log entries are added
    for auditing.
    """

    settings = get_settings()
    effective_today: date | None = None
    if settings.test_mode_enabled and getattr(user, "admin", False):
        effective_today = simulated_today

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

    status_code_value = await resolve_visit_status(db, visit, today=effective_today)
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

    cluster = visit.cluster
    project: Project | None = getattr(cluster, "project", None)

    await log_activity(
        db,
        actor_id=user_id,
        action="visit_takeover_accepted",
        target_type="visit",
        target_id=visit.id,
        details={
            "previous_researcher_id": advertiser_id,
            "new_researcher_id": user_id,
            "project_code": project.code if project else None,
            "cluster_number": cluster.cluster_number if cluster else None,
            "visit_nr": visit.visit_nr,
        },
        commit=False,
    )
    await log_activity(
        db,
        actor_id=user_id,
        action="visit_advertised_cancelled",
        target_type="visit",
        target_id=visit.id,
        details={
            "project_code": project.code if project else None,
            "cluster_number": cluster.cluster_number if cluster else None,
            "visit_nr": visit.visit_nr,
        },
        commit=False,
    )

    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
