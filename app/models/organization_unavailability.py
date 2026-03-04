from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin, SoftDeleteMixin


class OrganizationUnavailability(TimestampMixin, SoftDeleteMixin, Base):
    """Organization-wide unavailability periods (e.g. public holidays, company events).

    When FEATURE_STRICT_AVAILABILITY is enabled, the planners will skip these
    days when assigning researchers to visits.

    Attributes:
        start_date: Start of the unavailability period.
        end_date: End of the unavailability period (inclusive).
        morning: True if mornings are unavailable.
        daytime: True if daytimes are unavailable.
        nighttime: True if evenings/nights are unavailable.
        description: Optional label, e.g. "Koningsdag", "Bedrijfsuitje".
        is_default: True if seeded automatically by the holiday reset scheduler.
    """

    __tablename__ = "organization_unavailabilities"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)

    morning: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    daytime: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    nighttime: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
