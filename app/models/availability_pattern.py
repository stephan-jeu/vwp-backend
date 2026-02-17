from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import ForeignKey, Integer, Date
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB

from app.models import Base, TimestampMixin, SoftDeleteMixin
from app.models.user import User


class AvailabilityPattern(TimestampMixin, SoftDeleteMixin, Base):
    """Configuration for strict availability patterns.

    Defines a period (start_date to end_date) during which a specific
    weekly schedule applies.

    Attributes:
        user_id: Foreign key to the `users` table.
        start_date: Start of the validity period.
        end_date: End of the validity period.
        max_visits_per_week: Optional cap on visits per week.
        schedule: JSON definition of availability per weekday.
                  Example:
                  {
                    "monday": ["morning", "nighttime"],
                    "tuesday": ["daytime"]
                  }
    """

    __tablename__ = "availability_patterns"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey(User.id), nullable=False, index=True
    )
    user: Mapped[User] = relationship(User)

    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)

    max_visits_per_week: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Schedule is a JSON object mapping day names to lists of parts of day
    # e.g. {"monday": ["morning", "nighttime"], ...}
    schedule: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
