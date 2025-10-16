from __future__ import annotations

from pydantic import BaseModel


class ProjectBase(BaseModel):
    code: str
    location: str
    google_drive_folder: str | None = None


class ProjectCreate(ProjectBase):
    pass


class ProjectRead(ProjectBase):
    id: int

    model_config = {"from_attributes": True}
