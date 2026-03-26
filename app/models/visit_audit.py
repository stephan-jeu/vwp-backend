from __future__ import annotations

from sqlalchemy import ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, TimestampMixin
from app.models.user import User


class VisitAudit(TimestampMixin, Base):
    """Stores the mutable audit record for a single visit.

    One record per visit (enforced by the unique constraint on visit_id).
    The audit content can be updated freely without polluting the ActivityLog.
    Status transitions are still recorded in the ActivityLog for traceability.

    Attributes:
        visit_id: FK to the visit being audited (unique — one audit per visit).
        status: Current audit status code. One of:
            - ``"approved"``        (groen  – Goedgekeurd)
            - ``"needs_action"``    (geel   – Actie nodig)
            - ``"provisional"``     (oranje – Voorlopig afgekeurd)
            - ``"rejected"``        (rood   – Afgekeurd)
        errors: JSON array of error entries. Each entry is a dict with keys:
            ``code`` (str), ``fixed`` (bool), ``action`` (str | None),
            ``remarks`` (str | None).
        species_functions: JSON object keyed by species slug (e.g.
            ``"huismus"``, ``"vleermuizen"``). Each value is a dict with keys
            ``functions`` (mapping of function slug → bool) and
            ``remarks`` (str | None).
        remarks: General free-text remarks from the auditor.
        remarks_outside_pg: Bijzonderheden buiten het plangebied.
        created_by_id: User who created this audit record.
        updated_by_id: User who last updated this audit record (nullable on
            first save, updated on each subsequent edit).
    """

    __tablename__ = "visit_audits"
    __table_args__ = (UniqueConstraint("visit_id", name="uq_visit_audits_visit_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    visit_id: Mapped[int] = mapped_column(
        ForeignKey("visits.id"), nullable=False, index=True
    )

    status: Mapped[str] = mapped_column(String(32), nullable=False)

    errors: Mapped[list | None] = mapped_column(JSON, nullable=True)
    species_functions: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    remarks: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    remarks_outside_pg: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    created_by_id: Mapped[int] = mapped_column(
        ForeignKey(User.id), nullable=False, index=True
    )
    created_by: Mapped[User] = relationship(User, foreign_keys=[created_by_id])

    updated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey(User.id), nullable=True, index=True
    )
    updated_by: Mapped[User | None] = relationship(User, foreign_keys=[updated_by_id])
