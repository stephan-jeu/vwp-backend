from typing import Type, TypeVar

from sqlalchemy import select
from sqlalchemy.sql import Select

from app.models import SoftDeleteMixin

T = TypeVar("T", bound=SoftDeleteMixin)


def select_active(entity: Type[T]) -> Select:
    """Create a SELECT statement that excludes soft-deleted records.

    This should be used instead of `select(Entity)` for any model that inherits
    from SoftDeleteMixin, to ensure `deleted_at IS NULL` is always applied.
    """
    return select(entity).where(entity.deleted_at.is_(None))
