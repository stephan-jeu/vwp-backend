from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, func, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""


class TimestampMixin:
    """Mixin that adds created_at and updated_at timestamps to models.

    - created_at: set once on insert (UTC)
    - updated_at: auto-updated on each update (UTC)
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )


class SoftDeleteMixin:
    """Mixin that adds soft-delete support via a nullable ``deleted_at`` timestamp.

    The presence of a non-null ``deleted_at`` indicates the row is soft-deleted.
    All application queries will exclude soft-deleted rows via a global
    with_loader_criteria filter registered on the async session.

    Attributes:
        deleted_at: Timestamp set to the UTC time when the row is soft-deleted.
    """

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )


class ArchivableMixin:
    """Mixin that adds archiving support via an ``is_archived`` boolean.
    
    Archived rows are hidden from standard application queries.
    """

    is_archived: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        index=True,
    )
