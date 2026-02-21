from __future__ import annotations

from sqlalchemy import String, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin, SoftDeleteMixin


class Project(TimestampMixin, SoftDeleteMixin, Base):
    """Project container.

    Attributes:
        code: Short code identifier.
        location: Human-friendly location string.
    """

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), index=True)
    location: Mapped[str] = mapped_column(String(255))
    customer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    google_drive_folder: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quote: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
