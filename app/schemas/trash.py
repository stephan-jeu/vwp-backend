from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class TrashKind(StrEnum):
    """Logical type of a soft-deleted entity in the admin trash.

    Values:
        PROJECT: Soft-deleted project.
        CLUSTER: Soft-deleted cluster.
        VISIT: Soft-deleted visit.
        USER: Soft-deleted user.
    """

    PROJECT = "project"
    CLUSTER = "cluster"
    VISIT = "visit"
    USER = "user"


class TrashItem(BaseModel):
    """Flattened representation of a soft-deleted entity for the admin UI.

    Args:
        id: Primary key of the entity.
        kind: Logical type of entity (project/cluster/visit/user).
        label: Human-readable label for display in the trash table.
        project_code: Optional project code for grouping and sorting.
        cluster_number: Optional cluster number within a project.
        visit_nr: Optional visit number within a cluster.
        deleted_at: Timestamp when the entity was soft-deleted.

    Returns:
        Pydantic model suitable for use in admin trash listings.
    """

    id: int
    kind: TrashKind
    label: str
    project_code: str | None = None
    cluster_number: int | None = None
    visit_nr: int | None = None
    deleted_at: datetime

    model_config = {"from_attributes": True}
