from __future__ import annotations

from datetime import date
from enum import Enum

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, TimestampMixin
from app.models.user import User
from app.models.visit import Visit


class VisitActionEnum(str, Enum):
    COMPLETED = "Completed"
    APPROVED = "Approved"
    REDO = "Redo"
    CANCELLED = "Cancelled"
    SCHEDULED = "Scheduled"


class DayPeriodEnum(str, Enum):
    MORNING = "morning"
    DAY = "day"
    EVENING = "evening"
    NIGHT = "night"


class VisitLog(TimestampMixin, Base):
    """Audit log for visits, capturing outcomes, statuses, and deviations.

    Args:
        visit_id: The linked visit primary key.
        action: The lifecycle event recorded for this log entry.
        researcher_id: Optional user responsible for the action or visit.
        visit_date: The date the visit occurred (for completed-like actions).
        day_period: Day period classification for the visit.
        deviated: Whether there was a deviation from the protocol.
        deviation_reason: Optional text describing the deviation and rationale.

    Returns:
        Persisted VisitLog rows for auditing and compliance checks.
    """

    __tablename__ = "visit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    visit_id: Mapped[int] = mapped_column(
        ForeignKey(Visit.id), nullable=False, index=True
    )
    visit: Mapped[Visit] = relationship(Visit)

    action: Mapped["VisitActionEnum"] = mapped_column(String(32), nullable=False)
    researcher_id: Mapped[int | None] = mapped_column(
        ForeignKey(User.id), nullable=True
    )
    researcher: Mapped[User | None] = relationship(User)

    visit_date: Mapped[date | None] = mapped_column(nullable=True)
    day_period: Mapped["DayPeriodEnum" | None] = mapped_column(
        String(16), nullable=True
    )

    deviated: Mapped[bool] = mapped_column(default=False, nullable=False)
    deviation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
