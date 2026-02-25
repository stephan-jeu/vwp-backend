from __future__ import annotations

from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, field_validator


class UserUnavailabilityBase(BaseModel):
    start_date: date
    end_date: date
    morning: bool = True
    daytime: bool = True
    nighttime: bool = True

    @field_validator("end_date")
    @classmethod
    def validate_date_order(cls, v: date, info) -> date:
        if "start_date" in info.data and v < info.data["start_date"]:
            raise ValueError("end_date must be after start_date")
        return v


class UserUnavailabilityCreate(UserUnavailabilityBase):
    pass


class UserUnavailabilityUpdate(BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    morning: bool | None = None
    daytime: bool | None = None
    nighttime: bool | None = None


class UserUnavailabilityOut(UserUnavailabilityBase):
    id: int
    user_id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
