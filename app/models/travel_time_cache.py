from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin


class TravelTimeCache(TimestampMixin, Base):
    """Cache for travel times between two locations.

    Attributes:
        origin: The starting address or coordinates.
        destination: The ending address or coordinates.
        travel_minutes: The travel time in minutes.
    """

    __tablename__ = "travel_time_cache"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    origin: Mapped[str] = mapped_column(String(255), index=True)
    destination: Mapped[str] = mapped_column(String(255), index=True)
    travel_minutes: Mapped[int] = mapped_column(Integer)
