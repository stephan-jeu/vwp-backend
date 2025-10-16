from __future__ import annotations

from pydantic import BaseModel, Field
from app.schemas.user import UserNameRead


class AvailabilityBase(BaseModel):
    """Shared fields for weekly availability entries."""

    user_id: int
    year: int = Field(ge=1)
    week: int = Field(ge=1, le=53)
    daytime_days: int = Field(default=0, ge=0, le=7)
    nighttime_days: int = Field(default=0, ge=0, le=7)
    flex_days: int = Field(default=0, ge=0, le=7)


class AvailabilityCreate(AvailabilityBase):
    """Payload for creating availability for a given user and week."""


class AvailabilityUpdate(BaseModel):
    """Partial update for availability days counts."""

    daytime_days: int | None = Field(default=None, ge=0, le=7)
    nighttime_days: int | None = Field(default=None, ge=0, le=7)
    flex_days: int | None = Field(default=None, ge=0, le=7)


class AvailabilityRead(AvailabilityBase):
    """Read model for weekly availability with nested lightweight user."""

    id: int
    user: UserNameRead | None = None

    model_config = {"from_attributes": True}
