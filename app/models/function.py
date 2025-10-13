from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models import Base, TimestampMixin


class Function(TimestampMixin, Base):
    """Function entity (purpose/category).

    Attributes:
        id: Primary key.
        name: Function name.
    """

    __tablename__ = "functions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)

