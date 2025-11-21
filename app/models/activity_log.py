from __future__ import annotations

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, TimestampMixin
from app.models.user import User


class ActivityLog(TimestampMixin, Base):
    """Generic audit log entry for important domain actions.

    This model replaces the visit-specific ``VisitLog`` and is intended to be
    used across projects, clusters, visits, users, planning runs, and other
    entities.

    Args:
        actor_id: Optional id of the user that performed the action. ``NULL``
            is allowed for system-initiated actions.
        action: Machine-friendly action label (e.g. ``"project_created"``,
            ``"cluster_created"``, ``"visit_executed"``).
        target_type: Logical target type of the action (e.g. ``"project"``,
            ``"cluster"``, ``"visit"``, ``"planning_week"``, ``"user"``).
        target_id: Optional primary key of the target entity when applicable.
        details: Optional JSON payload with structured context such as
            ``{"visits_created": [101, 102]}``.
        batch_id: Optional correlation identifier used to group multiple log
            entries that belong to a single high-level operation.

    Returns:
        Persisted ``ActivityLog`` rows for auditing and reporting.
    """

    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey(User.id), nullable=True, index=True
    )
    actor: Mapped[User | None] = relationship(User)

    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_id: Mapped[int | None] = mapped_column(nullable=True, index=True)

    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    batch_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
