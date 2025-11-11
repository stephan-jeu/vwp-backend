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
        MEDIOR = "Medior"
        SENIOR = "Senior"

    contract: ContractType | None = None
    experience_bat: ExperienceBat | None = None
    smp: bool = False
    pad: bool = False
    langoor: bool = False
    roofvogel: bool = False
    wbc: bool = False
    fiets: bool = False
    hub: bool = False
    dvp: bool = False
    vrfg: bool = False
    vleermuis: bool = False
    zwaluw: bool = False
    vlinder: bool = False
    zangvogel: bool = False
    biggenkruid: bool = False
    schijfhoren: bool = False


class UserCreate(UserBase):
    pass


class UserRead(UserBase):
    id: int

    model_config = {
        "from_attributes": True,
    }


class UserUpdate(BaseModel):
    """Partial update schema for users."""

    email: EmailStr | None = None
    full_name: str | None = None
    admin: bool | None = None
    city: str | None = None
    contract: UserBase.ContractType | None = None
    experience_bat: UserBase.ExperienceBat | None = None
    smp: bool | None = None
    pad: bool | None = None
    langoor: bool | None = None
    roofvogel: bool | None = None
    wbc: bool | None = None
    fiets: bool | None = None
    hub: bool | None = None
    dvp: bool | None = None
    vrfg: bool | None = None
    vleermuis: bool | None = None
    zwaluw: bool | None = None
    vlinder: bool | None = None
    zangvogel: bool | None = None
    biggenkruid: bool | None = None
    schijfhoren: bool | None = None


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
