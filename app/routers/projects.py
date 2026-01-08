from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status, Response
from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectRead
from app.services.security import require_admin
from app.services.soft_delete import soft_delete_entity
from app.services.activity_log_service import log_activity
from db.session import get_db


router = APIRouter()


DbDep = Annotated[AsyncSession, Depends(get_db)]
AdminDep = Annotated[User, Depends(require_admin)]


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
async def create_project(admin: AdminDep, db: DbDep, payload: ProjectCreate) -> Project:
    """Create a new project.

    Returns 409 if a project with the same code already exists.
    """

    project = Project(
        code=payload.code,
        location=payload.location,
        google_drive_folder=payload.google_drive_folder,
        quote=payload.quote,
    )
    db.add(project)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT)
    await db.refresh(project)

    # Log project creation for audit trail
    await log_activity(
        db,
        actor_id=admin.id,
        action="project_created",
        target_type="project",
        target_id=project.id,
        details={
            "code": project.code,
            "location": project.location,
        },
    )

    return project


@router.put("/{project_id}", response_model=ProjectRead)
async def update_project(
    admin: AdminDep,
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
    project.quote = payload.quote
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT)
    await db.refresh(project)

    return project


@router.delete(
    "/{project_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response
)
async def delete_project(
    admin: AdminDep, db: DbDep, project_id: Annotated[int, Path(ge=1)]
) -> Response:
    """Delete a project by id.

    Rely on DB-level cascade to remove dependent rows.
    Returns 404 if not found.
    """

    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    await soft_delete_entity(db, project, cascade=True)
    await db.commit()

    await log_activity(
        db,
        actor_id=admin.id,
        action="project_deleted",
        target_type="project",
        target_id=project_id,
        details={
            "code": getattr(project, "code", None),
            "location": getattr(project, "location", None),
        },
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
