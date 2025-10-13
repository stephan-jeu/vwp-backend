from __future__ import annotations

from pydantic import BaseModel


class FamilyBase(BaseModel):
    name: str


class FamilyCreate(FamilyBase):
    pass


class FamilyRead(FamilyBase):
    id: int

    model_config = {"from_attributes": True}

