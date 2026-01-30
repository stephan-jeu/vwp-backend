from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import Select, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SoftDeleteMixin
from app.models.activity_log import ActivityLog
from app.models.availability import AvailabilityWeek
from app.models.cluster import Cluster
from app.models.project import Project
from app.models.user import User
from app.models.visit import (
    Visit,
    visit_functions,
    visit_protocol_visit_windows,
    visit_researchers,
    visit_species,
)
from app.schemas.trash import TrashItem, TrashKind
from app.services.soft_delete import _CASCADE_MAP


async def list_trash_items(db: AsyncSession) -> list[TrashItem]:
    """Return a flattened list of top-level soft-deleted entities.

    Top-level entities are:

    * Projects: any soft-deleted project.
    * Clusters: soft-deleted clusters whose parent project is not soft-deleted.
    * Visits: soft-deleted visits whose parent cluster is not soft-deleted.
    * Users: soft-deleted users.

    For projects, aggregated counts of soft-deleted clusters and visits under
    the project are included in the label so the admin UI can display e.g.
    ``P-001 (3 clusters, 20 bezoeken)``. For clusters, the label includes the
    number of soft-deleted child visits, e.g. ``P-001 - 5 (2 bezoeken)``.

    Args:
        db: Async SQLAlchemy session.

    Returns:
        List of :class:`TrashItem` rows sorted by ``deleted_at`` (newest first).
    """

    items: list[TrashItem] = []

    # Projects (top-level), with aggregated counts of soft-deleted children
    proj_stmt: Select[tuple[int, str, datetime]] = (
        select(Project.id, Project.code, Project.deleted_at)
        .execution_options(include_deleted=True)
        .where(Project.deleted_at.is_not(None))
    )
    proj_rows = (await db.execute(proj_stmt)).all()
    project_ids = [pid for pid, _, _ in proj_rows]

    cluster_counts: dict[int, int] = {}
    visit_counts: dict[int, int] = {}

    if project_ids:
        # Count soft-deleted clusters per project
        cl_counts_stmt: Select[tuple[int, int]] = (
            select(Cluster.project_id, func.count())
            .execution_options(include_deleted=True)
            .where(Cluster.project_id.in_(project_ids))
            .where(Cluster.deleted_at.is_not(None))
            .group_by(Cluster.project_id)
        )
        for project_id, count in (await db.execute(cl_counts_stmt)).all():
            cluster_counts[int(project_id)] = int(count)

        # Count soft-deleted visits per project via clusters
        visit_counts_stmt: Select[tuple[int, int]] = (
            select(Cluster.project_id, func.count(Visit.id))
            .join(Cluster, Visit.cluster_id == Cluster.id)
            .execution_options(include_deleted=True)
            .where(Cluster.project_id.in_(project_ids))
            .where(Visit.deleted_at.is_not(None))
            .group_by(Cluster.project_id)
        )
        for project_id, count in (await db.execute(visit_counts_stmt)).all():
            visit_counts[int(project_id)] = int(count)

    for pid, code, deleted_at in proj_rows:
        clusters = cluster_counts.get(pid, 0)
        visits = visit_counts.get(pid, 0)
        label = f"{code} ({clusters} clusters, {visits} bezoeken)"
        items.append(
            TrashItem(
                id=pid,
                kind=TrashKind.PROJECT,
                label=label,
                project_code=code,
                deleted_at=deleted_at,
            )
        )

    # Clusters (top-level): soft-deleted clusters on active projects
    cl_stmt: Select[tuple[int, int, str, datetime]] = (
        select(Cluster.id, Cluster.cluster_number, Project.code, Cluster.deleted_at)
        .join(Project, Cluster.project_id == Project.id)
        .execution_options(include_deleted=True)
        .where(Cluster.deleted_at.is_not(None))
        .where(Project.deleted_at.is_(None))
    )
    cl_rows = (await db.execute(cl_stmt)).all()
    cluster_ids = [cid for cid, _, _, _ in cl_rows]

    visit_counts_by_cluster: dict[int, int] = {}
    if cluster_ids:
        visit_counts_cluster_stmt: Select[tuple[int, int]] = (
            select(Visit.cluster_id, func.count(Visit.id))
            .execution_options(include_deleted=True)
            .where(Visit.cluster_id.in_(cluster_ids))
            .where(Visit.deleted_at.is_not(None))
            .group_by(Visit.cluster_id)
        )
        for cluster_id, count in (await db.execute(visit_counts_cluster_stmt)).all():
            visit_counts_by_cluster[int(cluster_id)] = int(count)

    for cid, cluster_number, project_code, deleted_at in cl_rows:
        visits = visit_counts_by_cluster.get(cid, 0)
        label = f"{project_code} - {cluster_number} ({visits} bezoeken)"
        items.append(
            TrashItem(
                id=cid,
                kind=TrashKind.CLUSTER,
                label=label,
                project_code=project_code,
                cluster_number=cluster_number,
                deleted_at=deleted_at,
            )
        )

    # Visits (top-level): soft-deleted visits on active clusters
    visit_stmt: Select[tuple[int, int | None, int, str, datetime]] = (
        select(
            Visit.id,
            Visit.visit_nr,
            Cluster.cluster_number,
            Project.code,
            Visit.deleted_at,
        )
        .join(Cluster, Visit.cluster_id == Cluster.id)
        .join(Project, Cluster.project_id == Project.id)
        .execution_options(include_deleted=True)
        .where(Visit.deleted_at.is_not(None))
        .where(Cluster.deleted_at.is_(None))
    )
    visit_rows = (await db.execute(visit_stmt)).all()
    for vid, visit_nr, cluster_number, project_code, deleted_at in visit_rows:
        label_visit_nr = "-" if visit_nr is None else str(visit_nr)
        label = f"{project_code} - {cluster_number} - {label_visit_nr}"
        items.append(
            TrashItem(
                id=vid,
                kind=TrashKind.VISIT,
                label=label,
                project_code=project_code,
                cluster_number=cluster_number,
                visit_nr=visit_nr,
                deleted_at=deleted_at,
            )
        )

    # Users (top-level)
    user_stmt: Select[tuple[int, str, str | None, datetime]] = (
        select(User.id, User.email, User.full_name, User.deleted_at)
        .execution_options(include_deleted=True)
        .where(User.deleted_at.is_not(None))
    )
    for uid, email, full_name, deleted_at in (await db.execute(user_stmt)).all():
        display_name = full_name or "(naam onbekend)"
        items.append(
            TrashItem(
                id=uid,
                kind=TrashKind.USER,
                label=f"{display_name} ({email})",
                deleted_at=deleted_at,
            )
        )

    items.sort(key=lambda x: x.deleted_at, reverse=True)
    return items


async def restore_trash_item(db: AsyncSession, kind: TrashKind, entity_id: int) -> None:
    """Restore a soft-deleted entity (and its configured children).

    Duplicate checks are performed for projects, clusters, visits and users to
    avoid restoring conflicting rows. On conflict, an HTTP 409 is raised so
    the UI can show an inline message.

    Args:
        db: Async SQLAlchemy session.
        kind: Logical kind of the entity to restore.
        entity_id: Primary key of the entity.

    Raises:
        HTTPException: 404 if the entity is not found, 409 on duplicate.
    """

    if kind is TrashKind.PROJECT:
        project = await _get_soft_deleted(db, Project, entity_id)
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        # Duplicate: same project code already active
        exists_stmt = (
            select(func.count())
            .select_from(Project)
            .where(Project.code == project.code)
            .where(Project.deleted_at.is_(None))
        )
        if (await db.execute(exists_stmt)).scalar_one() > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Er bestaat al een project met deze code.",
            )

        await _restore_entity_with_children(db, project)
        await db.commit()
        return

    if kind is TrashKind.CLUSTER:
        cluster = await _get_soft_deleted(db, Cluster, entity_id)
        if cluster is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        # Duplicate: same project + cluster_number already active
        exists_stmt = (
            select(func.count())
            .select_from(Cluster)
            .where(Cluster.project_id == cluster.project_id)
            .where(Cluster.cluster_number == cluster.cluster_number)
            .where(Cluster.deleted_at.is_(None))
        )
        if (await db.execute(exists_stmt)).scalar_one() > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Er bestaat al een cluster met dit clusternummer voor dit project.",
            )

        await _restore_entity_with_children(db, cluster)
        await db.commit()
        return

    if kind is TrashKind.VISIT:
        visit = await _get_soft_deleted(db, Visit, entity_id)
        if visit is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        # Duplicate: same cluster + visit_nr already active (if visit_nr is set)
        if visit.visit_nr is not None:
            exists_stmt = (
                select(func.count())
                .select_from(Visit)
                .where(Visit.cluster_id == visit.cluster_id)
                .where(Visit.visit_nr == visit.visit_nr)
                .where(Visit.deleted_at.is_(None))
            )
            if (await db.execute(exists_stmt)).scalar_one() > 0:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Er bestaat al een bezoek met dit nummer in deze cluster.",
                )

        await _restore_entity_with_children(db, visit)
        await db.commit()
        return

    if kind is TrashKind.USER:
        user = await _get_soft_deleted(db, User, entity_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        # Duplicate: same email or same full name already active
        conditions = [User.email == user.email]
        if user.full_name:
            conditions.append(User.full_name == user.full_name)

        or_filter = or_(*conditions)
        exists_stmt = (
            select(func.count())
            .select_from(User)
            .where(User.deleted_at.is_(None))
            .where(or_filter)
        )

        if (await db.execute(exists_stmt)).scalar_one() > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Er bestaat al een iemand met deze naam of dit e-mailadres.",
            )

        await _restore_entity_with_children(db, user)
        await db.commit()
        return

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)


async def hard_delete_trash_item(
    db: AsyncSession, kind: TrashKind, entity_id: int
) -> None:
    """Permanently delete an entity and its children.

    This bypasses soft-delete semantics and removes the row plus configured
    children from the database.

    Args:
        db: Async SQLAlchemy session.
        kind: Logical kind of the entity to hard delete.
        entity_id: Primary key of the entity.

    Raises:
        HTTPException: 404 if the entity is not found.
    """

    if kind is TrashKind.VISIT:
        visit = await db.get(Visit, entity_id)
        if visit is None:
            # Also allow deleting from the deleted set
            visit = await _get_soft_deleted(db, Visit, entity_id)
        if visit is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        await _hard_delete_visits(db, [visit.id])
        await db.commit()
        return

    if kind is TrashKind.CLUSTER:
        cluster = await db.get(Cluster, entity_id)
        if cluster is None:
            cluster = await _get_soft_deleted(db, Cluster, entity_id)
        if cluster is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        # Collect visits in this cluster
        visit_ids = await _collect_visit_ids_for_clusters(db, [cluster.id])
        if visit_ids:
            await _hard_delete_visits(db, visit_ids)

        await db.execute(delete(Cluster).where(Cluster.id == cluster.id))
        await db.commit()
        return

    if kind is TrashKind.PROJECT:
        project = await db.get(Project, entity_id)
        if project is None:
            project = await _get_soft_deleted(db, Project, entity_id)
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        # Collect clusters and visits under this project
        cl_stmt: Select[tuple[int]] = (
            select(Cluster.id)
            .execution_options(include_deleted=True)
            .where(Cluster.project_id == project.id)
        )
        cluster_ids = [row[0] for row in (await db.execute(cl_stmt)).all()]

        if cluster_ids:
            visit_ids = await _collect_visit_ids_for_clusters(db, cluster_ids)
            if visit_ids:
                await _hard_delete_visits(db, visit_ids)
            await db.execute(delete(Cluster).where(Cluster.id.in_(cluster_ids)))

        await db.execute(delete(Project).where(Project.id == project.id))
        await db.commit()
        return

    if kind is TrashKind.USER:
        user = await db.get(User, entity_id)
        if user is None:
            user = await _get_soft_deleted(db, User, entity_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        # Remove references from activity logs and visits, then delete availability
        await db.execute(
            update(ActivityLog)
            .where(ActivityLog.actor_id == user.id)
            .values(actor_id=None)
        )
        await db.execute(
            delete(visit_researchers).where(visit_researchers.c.user_id == user.id)
        )
        await db.execute(
            delete(AvailabilityWeek).where(AvailabilityWeek.user_id == user.id)
        )
        await db.execute(delete(User).where(User.id == user.id))
        await db.commit()
        return

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)


async def _get_soft_deleted(
    db: AsyncSession, model: type[SoftDeleteMixin], entity_id: int
) -> SoftDeleteMixin | None:
    stmt: Select[tuple[SoftDeleteMixin]] = (
        select(model)
        .execution_options(include_deleted=True)
        .where(model.id == entity_id)
    )
    return (await db.execute(stmt)).scalars().first()


async def _restore_entity_with_children(
    db: AsyncSession, instance: SoftDeleteMixin
) -> None:
    now = datetime.now(timezone.utc)
    setattr(instance, "deleted_at", None)

    # Restore configured children using the same cascade map as soft-delete
    await _restore_children(db, type(instance), [getattr(instance, "id")], now)


async def _restore_children(
    db: AsyncSession, parent_model: type[object], parent_ids: list[int], now: datetime
) -> None:
    children = _CASCADE_MAP.get(parent_model) or []
    for child_model, fk_col in children:
        id_col = getattr(child_model, "id")
        # Un-delete children for these parents
        await db.execute(
            update(child_model)
            .where(fk_col.in_(parent_ids))
            .where(getattr(child_model, "deleted_at").is_not(None))
            .values(deleted_at=None, updated_at=now)
        )
        # Recurse if the child also has children configured
        if _CASCADE_MAP.get(child_model):
            res = await db.execute(select(id_col).where(fk_col.in_(parent_ids)))
            next_ids = [row[0] for row in res.all()]
            if next_ids:
                await _restore_children(db, child_model, next_ids, now)


async def _collect_visit_ids_for_clusters(
    db: AsyncSession, cluster_ids: list[int]
) -> list[int]:
    stmt: Select[tuple[int]] = (
        select(Visit.id)
        .execution_options(include_deleted=True)
        .where(Visit.cluster_id.in_(cluster_ids))
    )
    return [row[0] for row in (await db.execute(stmt)).all()]


async def _hard_delete_visits(db: AsyncSession, visit_ids: list[int]) -> None:
    if not visit_ids:
        return

    await db.execute(
        delete(visit_functions).where(visit_functions.c.visit_id.in_(visit_ids))
    )
    await db.execute(
        delete(visit_species).where(visit_species.c.visit_id.in_(visit_ids))
    )
    await db.execute(
        delete(visit_researchers).where(visit_researchers.c.visit_id.in_(visit_ids))
    )
    await db.execute(
        delete(visit_protocol_visit_windows).where(
            visit_protocol_visit_windows.c.visit_id.in_(visit_ids)
        )
    )
    await db.execute(delete(Visit).where(Visit.id.in_(visit_ids)))
