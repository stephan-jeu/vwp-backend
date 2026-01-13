from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple, Type, Sequence

from sqlalchemy import update, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SoftDeleteMixin
from app.models.project import Project
from app.models.cluster import Cluster
from app.models.visit import Visit
from app.models.availability import AvailabilityWeek
from app.models.user import User

# Map parent model -> list of (child model, child FK column referencing parent.id)
_CASCADE_MAP: Dict[Type[Any], List[Tuple[Type[Any], Any]]] = {
    Project: [(Cluster, Cluster.project_id)],
    Cluster: [(Visit, Visit.cluster_id)],
    User: [(AvailabilityWeek, AvailabilityWeek.user_id)],
}


async def soft_delete_entity(
    db: AsyncSession, instance: SoftDeleteMixin, cascade: bool = True
) -> None:
    """Soft-delete an ORM instance and optionally cascade to configured children.

    Args:
        db: Async SQLAlchemy session.
        instance: The ORM instance to soft-delete.
        cascade: Whether to cascade soft-delete to configured child rows.

    Returns:
        None. The caller is responsible for committing the transaction.
    """
    now = datetime.now(timezone.utc)
    setattr(instance, "deleted_at", now)

    if not cascade:
        return

    # Depth-first recursive cascade without loading ORM instances
    await _cascade_children(db, type(instance), [getattr(instance, "id")], now)


async def _cascade_children(
    db: AsyncSession, parent_model: Type[Any], parent_ids: Sequence[int], now: datetime
) -> None:
    children = _CASCADE_MAP.get(parent_model) or []
    for child_model, fk_col in children:
        # Collect child ids for next level
        id_col = getattr(child_model, "id")
        # Soft-delete all children for these parents
        await db.execute(
            update(child_model)
            .where(fk_col.in_(parent_ids))
            .where(getattr(child_model, "deleted_at").is_(None))
            .values(deleted_at=now)
        )
        # Recurse if the child also has configured children
        if _CASCADE_MAP.get(child_model):
            res = await db.execute(
                select(id_col)
                .where(fk_col.in_(parent_ids))
                .execution_options(include_deleted=True)
            )
            next_ids = [row[0] for row in res.all()]
            if next_ids:
                await _cascade_children(db, child_model, next_ids, now)
