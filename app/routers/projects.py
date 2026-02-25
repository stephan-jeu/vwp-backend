from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, status, Response
from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError

from app.deps import AdminDep, DbDep
from app.db.utils import select_active
from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectRead, ProjectBulkArchive
from app.services.soft_delete import soft_delete_entity
from app.services.activity_log_service import log_activity
from sqlalchemy import update
from app.models.cluster import Cluster
from app.models.visit import Visit


router = APIRouter()


@router.get("", response_model=list[ProjectRead])
async def list_projects(_: AdminDep, db: DbDep) -> list[Project]:
    """Return all projects.

    Args:
        _: Ensures only admins can access.
        db: Async SQLAlchemy session.

    Returns:
        List of `Project` rows.
    """

    stmt: Select[tuple[Project]] = select_active(Project).order_by(Project.code)
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
        customer=payload.customer,
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
    project.customer = payload.customer
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


@router.post("/bulk-archive", status_code=status.HTTP_200_OK)
async def bulk_archive_projects(
    admin: AdminDep, db: DbDep, payload: ProjectBulkArchive
) -> dict[str, int]:
    """Archive multiple projects and cascade to underlying clusters/visits."""

    if not payload.project_ids:
        return {"archived_projects": 0}

    # Verify projects exist and get their cluster IDs
    stmt_clusters = select(Cluster.id).where(
        Cluster.project_id.in_(payload.project_ids),
        Cluster.deleted_at.is_(None)
    )
    cluster_result = await db.execute(stmt_clusters)
    cluster_ids = [row[0] for row in cluster_result.all()]

    # 1. Archive Projects
    stmt_upd_proj = (
        update(Project)
        .where(Project.id.in_(payload.project_ids))
        .values(is_archived=True)
    )
    await db.execute(stmt_upd_proj)

    # 2. Archive Clusters
    if cluster_ids:
        stmt_upd_clust = (
            update(Cluster)
            .where(Cluster.project_id.in_(payload.project_ids))
            .values(is_archived=True)
        )
        await db.execute(stmt_upd_clust)

        # 3. Archive Visits
        stmt_upd_visits = (
            update(Visit)
            .where(Visit.cluster_id.in_(cluster_ids))
            .values(is_archived=True)
        )
        await db.execute(stmt_upd_visits)

    await db.commit()

    # Log activity for each archived project
    for pid in payload.project_ids:
        await log_activity(
            db,
            actor_id=admin.id,
            action="project_archived",
            target_type="project",
            target_id=pid,
            details={"bulk": True},
        )

    return {"archived_projects": len(payload.project_ids)}
