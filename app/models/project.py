from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin


class Project(TimestampMixin, Base):
    """Project container.

    Attributes:
        code: Short code identifier.
        location: Human-friendly location string.
    """

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    location: Mapped[str] = mapped_column(String(255))
    google_drive_folder: Mapped[str | None] = mapped_column(String(255), nullable=True)
