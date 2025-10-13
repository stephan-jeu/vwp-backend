from __future__ import annotations

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models import Base, TimestampMixin
from backend.app.models.family import Family


class Species(TimestampMixin, Base):
    """Species entity.

    Attributes:
        id: Primary key.
        name: Common name.
        name_latin: Latin name.
    """

    __tablename__ = "species"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    family_id: Mapped[int] = mapped_column(
        ForeignKey(Family.id), nullable=False, index=True
    )
    family: Mapped[Family] = relationship(Family)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name_latin: Mapped[str] = mapped_column(String(255), unique=True, index=True)
