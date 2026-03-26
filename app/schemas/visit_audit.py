from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.schemas.user import UserNameRead


class AuditStatus(StrEnum):
    APPROVED = "approved"
    NEEDS_ACTION = "needs_action"
    PROVISIONAL = "provisional"
    REJECTED = "rejected"


class AuditErrorEntry(BaseModel):
    """A single error entry within a visit audit.

    Attributes:
        code: Machine-readable error code (e.g. ``"no_visit_summary"``).
        fixed: Whether the error has been corrected by the researcher.
        action: Optional action taken by the auditor (e.g. ``"pl_emailed"``).
        remarks: Optional free-text note for this specific error.
    """

    code: str
    fixed: bool = False
    action: str | None = None
    remarks: str | None = None


class SpeciesFunctionEntry(BaseModel):
    """Audit data for a single species/soortgroep in the plangebied.

    Attributes:
        functions: Mapping of function slug to whether it was found
            (e.g. ``{"nestplaats": True, "functioneel_leefgebied": False}``).
        remarks: Optional free-text note (e.g. species name, counts).
    """

    functions: dict[str, bool] = Field(default_factory=dict)
    remarks: str | None = None


class VisitAuditWrite(BaseModel):
    """Payload for creating or updating a visit audit record.

    All fields except ``status`` are optional so partial saves are possible
    while filling in the form.

    Attributes:
        status: Audit outcome. Required — determines tab placement and colours.
        errors: List of error entries, each with code, fixed flag, action, and
            remarks.
        species_functions: Keyed by species slug; value contains function
            checkboxes and remarks.
        remarks: General auditor remarks (Opmerkingen).
        remarks_outside_pg: Notes about findings outside the plangebied.
    """

    status: AuditStatus
    errors: list[AuditErrorEntry] = Field(default_factory=list)
    species_functions: dict[str, SpeciesFunctionEntry] = Field(default_factory=dict)
    remarks: str | None = None
    remarks_outside_pg: str | None = None


class VisitAuditRead(BaseModel):
    """Full audit record returned by the API.

    Attributes:
        id: Primary key of the audit record.
        visit_id: FK to the audited visit.
        status: Current audit status code.
        errors: List of error entries.
        species_functions: Keyed species/function data.
        remarks: General auditor remarks.
        remarks_outside_pg: Notes outside the plangebied.
        created_by: User who created the audit.
        updated_by: User who last updated the audit, if applicable.
        created_at: Timestamp of the first save.
        updated_at: Timestamp of the last save.
    """

    id: int
    visit_id: int
    status: AuditStatus
    errors: list[AuditErrorEntry] = []
    species_functions: dict[str, SpeciesFunctionEntry] = {}
    remarks: str | None = None
    remarks_outside_pg: str | None = None
    created_by: UserNameRead
    updated_by: UserNameRead | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
