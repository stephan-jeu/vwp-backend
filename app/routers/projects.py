from __future__ import annotations

from typing import Annotated, Sequence

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectRead
from app.services.security import require_admin
from db.session import get_db


router = APIRouter()


DbDep = Annotated[AsyncSession, Depends(get_db)]
AdminDep = Annotated[object, Depends(require_admin)]


@router.get("", response_model=list[ProjectRead])
async def list_projects(_: AdminDep, db: DbDep) -> list[Project]:
    """Return all projects.

    Args:
        _: Ensures only admins can access.
        db: Async SQLAlchemy session.

    Returns:
        List of `Project` rows.
    """

    stmt: Select[tuple[Project]] = select(Project).order_by(Project.code)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(_: AdminDep, db: DbDep, payload: ProjectCreate) -> Project:
    """Create a new project.

    Returns 409 if a project with the same code already exists.
    """

    project = Project(
        code=payload.code,
        location=payload.location,
        google_drive_folder=payload.google_drive_folder,
    )
    db.add(project)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT)
    await db.refresh(project)
    return project


@router.put("/{project_id}", response_model=ProjectRead)
async def update_project(
    _: AdminDep,
    db: DbDep,
    payload: ProjectCreate,
    project_id: Annotated[int, Path(ge=1)],
) -> Project:
    """Update an existing project by id.

    Returns 404 if not found. Returns 409 on unique code conflict.
    """

    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    project.code = payload.code
    project.location = payload.location
    project.google_drive_folder = payload.google_drive_folder
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT)
    await db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    _: AdminDep, db: DbDep, project_id: Annotated[int, Path(ge=1)]
) -> None:
    """Delete a project by id.

    Rely on DB-level cascade to remove dependent rows.
    Returns 404 if not found.
    """

    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await db.delete(project)
    await db.commit()
    return None
