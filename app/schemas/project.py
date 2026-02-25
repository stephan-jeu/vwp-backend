from __future__ import annotations

from pydantic import BaseModel


class ProjectBase(BaseModel):
    code: str
    location: str
    customer: str | None = None
    google_drive_folder: str | None = None
    quote: bool = False


class ProjectCreate(ProjectBase):
    pass


class ProjectRead(ProjectBase):
    id: int

    model_config = {"from_attributes": True}


class ProjectBulkArchive(BaseModel):
    project_ids: list[int]
