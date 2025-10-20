from __future__ import annotations

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, TimestampMixin
from app.models.project import Project


class Cluster(TimestampMixin, Base):
    """Cluster within a project.

    Attributes:
        project_id: Foreign key to parent project.
        address: Address string.
    """

    __tablename__ = "clusters"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey(Project.id), nullable=False, index=True
    )
    project: Mapped[Project] = relationship(Project)
    address: Mapped[str] = mapped_column(String(255))
    cluster_number: Mapped[int] = mapped_column(nullable=False, index=True)
