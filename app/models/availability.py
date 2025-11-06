from __future__ import annotations

from sqlalchemy import ForeignKey, UniqueConstraint, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, TimestampMixin
from app.models.user import User


class AvailabilityWeek(TimestampMixin, Base):
    """Weekly availability for a researcher.

    One row per (user, ISO week). Stores number of available days per
    slot type: morning, nighttime, and flex (either).

    Attributes:
        user_id: Foreign key to the `users` table.
        week: ISO week number (1-53).
        morning_days: Number of morning-available days in the week.
        nighttime_days: Number of nighttime-available days in the week.
        flex_days: Number of flex-available days in the week.
    """

    __tablename__ = "availability_weeks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey(User.id), nullable=False, index=True
    )
    user: Mapped[User] = relationship(User)

    week: Mapped[int] = mapped_column(Integer, nullable=False)
    
    morning_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    nighttime_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    flex_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("user_id", "week", name="uq_user_week"),
    )
