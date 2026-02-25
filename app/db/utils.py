from typing import Type, TypeVar

from sqlalchemy import select
from sqlalchemy.sql import Select

from app.models import SoftDeleteMixin

T = TypeVar("T", bound=SoftDeleteMixin)


def select_active(entity: Type[T], include_archived: bool = False) -> Select:
    """Create a SELECT statement that excludes soft-deleted records.

    This should be used instead of `select(Entity)` for any model that inherits
    from SoftDeleteMixin, to ensure `deleted_at IS NULL` is always applied.
    
    If the entity also supports Archiving (has `is_archived`), those are hidden
    unless `include_archived=True`.
    """
    stmt = select(entity).where(entity.deleted_at.is_(None))
    
    if not include_archived and hasattr(entity, "is_archived"):
        stmt = stmt.where(entity.is_archived.is_(False))
        
    return stmt
