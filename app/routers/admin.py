from __future__ import annotations

from typing import Annotated
from datetime import date

from fastapi import APIRouter, HTTPException, Path, Query, Response, status
from sqlalchemy import Select, func, select
from sqlalchemy.orm import selectinload

from app.models.activity_log import ActivityLog
from app.models.function import Function
from app.models.species import Species
from app.models.user import User
from app.schemas.activity_log import ActivityLogListResponse
from app.schemas.planning import SeasonPlannerStatusRead
from app.schemas.capacity import CapacitySimulationResponse
from app.schemas.function import FunctionRead
from app.schemas.species import SpeciesRead
from app.schemas.user import UserNameRead, UserRead, UserCreate, UserUpdate
from app.schemas.trash import TrashItem, TrashKind
from app.services.activity_log_service import log_activity
from app.services.season_planning_service import SeasonPlanningService
from app.services.planning_run_errors import PlanningRunError
from app.deps import AdminDep, DbDep
from app.services.user_service import (
    list_users_full as svc_list_users_full,
    create_user as svc_create_user,
    update_user as svc_update_user,
    delete_user as svc_delete_user,
)
from app.services.trash_service import (
    list_trash_items as svc_list_trash_items,
    restore_trash_item as svc_restore_trash_item,
    hard_delete_trash_item as svc_hard_delete_trash_item,
)
from app.services.tight_visits import get_tight_visit_chains, TightVisitResponse
from core.settings import get_settings


router = APIRouter()

_settings = get_settings()


@router.get("/tight-visits", response_model=list[TightVisitResponse])
async def list_tight_visits(
    _: AdminDep, db: DbDep, simulated_today: date | None = Query(None)
) -> list[TightVisitResponse]:
    """Identify and return 'tight' visit chains."""
    return await get_tight_visit_chains(db, simulated_today=simulated_today)


@router.get("")
async def admin_status() -> dict[str, str]:
    """Return admin status placeholder."""
    return {"status": "admin-ok"}


@router.get("/season-planner/status", response_model=SeasonPlannerStatusRead)
async def get_season_planner_status(
    _: AdminDep,
    db: DbDep,
) -> SeasonPlannerStatusRead:
    """Return last run metadata for the season planner.

    Args:
        _: Ensures the caller is an admin user.
        db: Async SQLAlchemy session.

    Returns:
        Timestamp of the most recent season planner run, if available.
    """

    stmt: Select[tuple[ActivityLog]] = (
        select(ActivityLog)
        .where(ActivityLog.action == "seasonal_planner_run")
        .order_by(ActivityLog.created_at.desc())
        .limit(1)
    )
    entry = (await db.execute(stmt)).scalars().first()
    return SeasonPlannerStatusRead(last_run_at=entry.created_at if entry else None)


@router.get("/activity", response_model=ActivityLogListResponse)
async def list_activity_logs(
    _: AdminDep,
    db: DbDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 10,
) -> ActivityLogListResponse:
    """Return a paginated list of recent activity log entries.

    Entries are ordered from newest to oldest so that the most recent
    actions are shown first on the admin dashboard.

    Args:
        _: Ensures the caller is an admin user.
        db: Async SQLAlchemy session.
        page: 1-based page number.
        page_size: Page size (max 50).

    Returns:
        Paginated :class:`ActivityLogListResponse` with recent entries.
    """

    count_stmt = select(func.count()).select_from(ActivityLog)
    total = int((await db.execute(count_stmt)).scalar_one())

    stmt: Select[tuple[ActivityLog]] = (
        select(ActivityLog)
        .options(selectinload(ActivityLog.actor), selectinload(ActivityLog.actors))
        .order_by(ActivityLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list((await db.execute(stmt)).scalars().all())

    return ActivityLogListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


# Helper _sim_result_to_response is no longer needed as SeasonPlanningService returns the schema directly


@router.get("/capacity/visits/families", response_model=CapacitySimulationResponse)
async def get_family_capacity(
    _: AdminDep,
    db: DbDep,
    include_quotes: Annotated[bool, Query()] = False,
    simulate: Annotated[bool, Query()] = False,
) -> CapacitySimulationResponse:
    """
    Get persisted Season Planning result.
    This replaces the legacy simulation. It reads validation weeks from visits.
    """
    # Simply read the grid. Start date defaults to today or start of year?
    # Simulation usually defaults to today.
    if simulate:
        return await SeasonPlanningService.simulate_capacity_grid(
            db, date.today(), include_quotes=include_quotes
        )
    return await SeasonPlanningService.get_capacity_grid(
        db, date.today(), include_quotes=include_quotes
    )


@router.post("/capacity/visits/families", response_model=CapacitySimulationResponse)
async def regenerate_family_capacity(
    admin: AdminDep,
    db: DbDep,
    include_quotes: Annotated[bool, Query()] = False,
    simulate: Annotated[bool, Query()] = False,
) -> CapacitySimulationResponse:
    """Run the Season Solver (Global Planning)."""

    if simulate:
        return await SeasonPlanningService.simulate_capacity_grid(
            db, date.today(), include_quotes=include_quotes
        )

    # Run Solver
    try:
        await SeasonPlanningService.run_season_solver(
            db,
            date.today(),
            include_quotes=False,
            persist=True,
            timeout_seconds=_settings.season_planner_timeout_quick_seconds,
        )
    except PlanningRunError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Het is niet gelukt om een goede capaciteitsplanning te maken. "
                "Probeer het later nog een keer."
            ),
        ) from exc
    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Het is niet gelukt om een goede capaciteitsplanning te maken. "
                "Probeer het later nog een keer."
            ),
        ) from exc

    # Return new state
    res = await SeasonPlanningService.get_capacity_grid(
        db, date.today(), include_quotes=False
    )

    await log_activity(
        db,
        actor_id=admin.id,
        action="seasonal_planner_run",
        target_type="system",
        target_id=0,  # No ID
        details={"method": "season_solver"},
    )

    return res


@router.get("/functions", response_model=list[FunctionRead])
async def list_functions(_: AdminDep, db: DbDep) -> list[Function]:
    """List all functions (admin only)."""
    stmt: Select[tuple[Function]] = select(Function).order_by(Function.name)
    return list((await db.execute(stmt)).scalars().all())


@router.get("/species", response_model=list[SpeciesRead])
async def list_species(_: AdminDep, db: DbDep) -> list[Species]:
    """List all species (admin only)."""
    stmt: Select[tuple[Species]] = (
        select(Species).options(selectinload(Species.family)).order_by(Species.name)
    )
    return list((await db.execute(stmt)).scalars().all())


@router.get("/users", response_model=list[UserNameRead])
async def list_users(_: AdminDep, db: DbDep) -> list[User]:
    """List all users (admin only) for selection menus."""
    stmt: Select[tuple[User]] = select(User).order_by(User.full_name)
    return list((await db.execute(stmt)).scalars().all())


@router.get("/users/all", response_model=list[UserRead])
async def list_users_full(
    _: AdminDep, db: DbDep, q: str | None = Query(None)
) -> list[User]:
    """List all users (admin only) with full details. Optional filter by name/email."""
    return await svc_list_users_full(db, q=q)


@router.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(admin: AdminDep, db: DbDep, payload: UserCreate) -> User:
    """Create a new user (admin only)."""

    user = await svc_create_user(db, payload)

    await log_activity(
        db,
        actor_id=admin.id,
        action="user_created",
        target_type="user",
        target_id=user.id,
        details={
            "email": user.email,
            "full_name": user.full_name,
        },
    )

    return user


@router.patch("/users/{user_id}", response_model=UserRead)
async def update_user(
    admin: AdminDep, db: DbDep, user_id: int, payload: UserUpdate
) -> User:
    """Update an existing user (admin only)."""

    user = await svc_update_user(db, user_id, payload)

    await log_activity(
        db,
        actor_id=admin.id,
        action="user_updated",
        target_type="user",
        target_id=user.id,
        details={
            "email": user.email,
            "full_name": user.full_name,
        },
    )

    return user


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(admin: AdminDep, db: DbDep, user_id: int) -> Response:
    """Delete a user (admin only)."""

    await svc_delete_user(db, user_id)

    await log_activity(
        db,
        actor_id=admin.id,
        action="user_deleted",
        target_type="user",
        target_id=user_id,
        details={},
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/trash", response_model=list[TrashItem])
async def list_trash(_: AdminDep, db: DbDep) -> list[TrashItem]:
    """List all soft-deleted entities for the admin trash view.

    Args:
        _: Ensures the caller is an admin user.
        db: Async SQLAlchemy session.

    Returns:
        List of :class:`TrashItem` rows representing soft-deleted entities.
    """

    return await svc_list_trash_items(db)


@router.post(
    "/trash/{kind}/{entity_id}/restore",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def restore_trash_item(
    admin: AdminDep,
    db: DbDep,
    kind: TrashKind,
    entity_id: Annotated[int, Path(ge=1)],
) -> Response:
    """Restore a soft-deleted entity and its children.

    Args:
        admin: Authenticated admin user performing the restore.
        db: Async SQLAlchemy session.
        kind: Logical type of entity to restore.
        entity_id: Primary key of the entity to restore.

    Returns:
        Empty 204 response on success.
    """

    await svc_restore_trash_item(db, kind=kind, entity_id=entity_id)

    await log_activity(
        db,
        actor_id=admin.id,
        action="trash_restored",
        target_type=str(kind.value),
        target_id=entity_id,
        details=None,
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/trash/{kind}/{entity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def hard_delete_trash_item(
    admin: AdminDep,
    db: DbDep,
    kind: TrashKind,
    entity_id: Annotated[int, Path(ge=1)],
) -> Response:
    """Permanently delete a soft-deleted entity and its children.

    Args:
        admin: Authenticated admin user performing the hard delete.
        db: Async SQLAlchemy session.
        kind: Logical type of entity to hard delete.
        entity_id: Primary key of the entity to delete.

    Returns:
        Empty 204 response on success.
    """

    await svc_hard_delete_trash_item(db, kind=kind, entity_id=entity_id)

    await log_activity(
        db,
        actor_id=admin.id,
        action="trash_hard_deleted",
        target_type=str(kind.value),
        target_id=entity_id,
        details=None,
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
