from __future__ import annotations

from pydantic import BaseModel


class SpeciesBase(BaseModel):
    family_id: int
    name: str
    name_latin: str | None = None
    abbreviation: str | None = None


class SpeciesCreate(SpeciesBase):
    pass


class SpeciesRead(SpeciesBase):
    id: int

    model_config = {"from_attributes": True}


class SpeciesCompactRead(BaseModel):
    """Compact species representation for nested read models.

    Args:
        id: Unique identifier of the species.
        name: Common name.
        abbreviation: Optional short code.

    Returns:
        Serialized compact species object.
    """

    id: int
    name: str
    abbreviation: str | None = None

    model_config = {"from_attributes": True}
