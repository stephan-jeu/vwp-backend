from __future__ import annotations

from datetime import date
from pydantic import BaseModel


class PlanningVisitRead(BaseModel):
    """Lightweight read model for planned visits used by the planning UI.

    Attributes:
        id: Visit id.
        project_code: Parent project short code.
        cluster_number: Cluster number within project.
        functions: Function names for the visit.
        species: Species names for the visit.
        from_date: Start of the visit window.
        to_date: End of the visit window.
        researchers: Assigned researcher display names.
    """

    id: int
    project_code: str
    cluster_number: int
    functions: list[str]
    species: list[str]
    from_date: date | None = None
    to_date: date | None = None
    researchers: list[str]

    model_config = {"from_attributes": True}
