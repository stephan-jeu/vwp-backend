from __future__ import annotations

from datetime import date

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, TimestampMixin
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from app.models.protocol import Protocol


class ProtocolVisitWindow(TimestampMixin, Base):
    """Per-visit date window for a protocol.

    Each instance represents a required or optional visit window within a protocol.
    Windows are ordered by ``visit_index`` (1-based) and may overlap or be identical.
    """

    __tablename__ = "protocol_visit_windows"
    __table_args__ = (
        UniqueConstraint("protocol_id", "visit_index", name="uq_protocol_visit_idx"),
        CheckConstraint("window_from <= window_to", name="ck_window_range_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    protocol_id: Mapped[int] = mapped_column(
        ForeignKey("protocols.id"), index=True, nullable=False
    )

    # 1-based visit index within a protocol
    visit_index: Mapped[int] = mapped_column(Integer, nullable=False)

    window_from: Mapped[date] = mapped_column(Date, nullable=False)
    window_to: Mapped[date] = mapped_column(Date, nullable=False)

    # Whether this window represents a required visit (vs. optional)
    required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    # Optional human-friendly label for UI (e.g., "June visit")
    label: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Relationship back to Protocol; defined as string to avoid import cycle
    protocol: Mapped["Protocol"] = relationship(
        "Protocol", back_populates="visit_windows"
    )
