from __future__ import annotations

from datetime import date

from sqlalchemy import ForeignKey, Date, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, TimestampMixin
from app.models.user import User


class UserUnavailability(TimestampMixin, Base):
    """Configuration for periods where a user is unavailable.

    Defines a period (start_date to end_date) during which a researcher is not available
    for visits. Can optionally be specific to mornings, daytimes, or nighttimes.

    Attributes:
        user_id: Foreign key to the `users` table.
        start_date: Start of the unavailability period.
        end_date: End of the unavailability period.
        morning: True if unavailable in the morning.
        daytime: True if unavailable during the day.
        nighttime: True if unavailable at night.
    """

    __tablename__ = "user_unavailabilities"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey(User.id), nullable=False, index=True
    )
    user: Mapped[User] = relationship(User)

    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)

    morning: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    daytime: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    nighttime: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
