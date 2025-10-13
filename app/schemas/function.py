from __future__ import annotations

from pydantic import BaseModel


class FunctionBase(BaseModel):
    name: str


class FunctionCreate(FunctionBase):
    pass


class FunctionRead(FunctionBase):
    id: int

    model_config = {"from_attributes": True}

