from __future__ import annotations

from pydantic import BaseModel


class FunctionBase(BaseModel):
    name: str


class FunctionCreate(FunctionBase):
    pass


class FunctionRead(FunctionBase):
    id: int

    model_config = {"from_attributes": True}


class FunctionCompactRead(BaseModel):
    """Compact function representation used in nested read models.

    Args:
        id: Unique identifier of the function.
        name: Human-readable function name.

    Returns:
        Serialized compact function object.
    """

    id: int
    name: str

    model_config = {"from_attributes": True}
