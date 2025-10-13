from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, EmailStr


class UserBase(BaseModel):
    email: EmailStr
    full_name: str | None = None
    admin: bool = False
    city: str | None = None

    class ContractType(StrEnum):
        INTERN = "Intern"
        FLEX = "Flex"
        ZZP = "ZZP"

    class ExperienceBat(StrEnum):
        NIEUW = "Nieuw"
        JUNIOR = "Junior"
        SENIOR = "Senior"
        GZ = "GZ"

    contract: ContractType | None = None
    experience_bat: ExperienceBat | None = None
    smp: bool = False
    rugstreeppad: bool = False
    huismus: bool = False
    langoren: bool = False
    roofvogels: bool = False
    wbc: bool = False
    fiets: bool = False
    hup: bool = False
    dvp: bool = False


class UserCreate(UserBase):
    password: str


class UserRead(UserBase):
    id: int

    model_config = {
        "from_attributes": True,
    }


class UserNameRead(BaseModel):
    """Lightweight user representation for display purposes.

    Args:
        id: Unique identifier of the user.
        full_name: Full name if available; used for UI display.

    Returns:
        Pydantic model suitable for nesting in other schemas.
    """

    id: int
    full_name: str | None = None

    model_config = {
        "from_attributes": True,
    }
