from __future__ import annotations

from pydantic import BaseModel


class SpeciesBase(BaseModel):
    family_id: int
    name: str
    name_latin: str


class SpeciesCreate(SpeciesBase):
    pass


class SpeciesRead(SpeciesBase):
    id: int

    model_config = {"from_attributes": True}
