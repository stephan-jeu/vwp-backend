from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models import Base, TimestampMixin


class Family(TimestampMixin, Base):
    """Taxonomic family entity.

    Attributes:
        id: Primary key.
        name: Family name.
    """

    __tablename__ = "families"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)

