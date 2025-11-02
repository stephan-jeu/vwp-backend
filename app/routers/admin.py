from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.function import Function
from app.models.species import Species
from app.models.user import User
from app.schemas.function import FunctionRead
from app.schemas.species import SpeciesRead
from app.schemas.user import UserNameRead
from app.services.security import require_admin
from db.session import get_db


router = APIRouter()


DbDep = Annotated[AsyncSession, Depends(get_db)]
AdminDep = Annotated[object, Depends(require_admin)]


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
