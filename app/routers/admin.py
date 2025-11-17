from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.function import Function
from app.models.species import Species
from app.models.user import User
from app.schemas.function import FunctionRead
from app.schemas.species import SpeciesRead
from app.schemas.user import UserNameRead, UserRead, UserCreate, UserUpdate
from app.services.activity_log_service import log_activity
from app.services.security import require_admin
from app.services.user_service import (
    list_users_full as svc_list_users_full,
    create_user as svc_create_user,
    update_user as svc_update_user,
    delete_user as svc_delete_user,
)
from db.session import get_db


router = APIRouter()


DbDep = Annotated[AsyncSession, Depends(get_db)]
AdminDep = Annotated[User, Depends(require_admin)]


@router.get("")
async def admin_status() -> dict[str, str]:
    """Return admin status placeholder."""
    return {"status": "admin-ok"}


@router.get("/functions", response_model=list[FunctionRead])
async def list_functions(_: AdminDep, db: DbDep) -> list[Function]:
    """List all functions (admin only)."""
    stmt: Select[tuple[Function]] = select(Function).order_by(Function.name)
    return list((await db.execute(stmt)).scalars().all())


@router.get("/species", response_model=list[SpeciesRead])
async def list_species(_: AdminDep, db: DbDep) -> list[Species]:
    """List all species (admin only)."""
    stmt: Select[tuple[Species]] = select(Species).order_by(Species.name)
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
