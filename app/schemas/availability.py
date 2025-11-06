from __future__ import annotations

from pydantic import BaseModel, Field
from app.schemas.user import UserNameRead
from typing import Literal


class AvailabilityBase(BaseModel):
    """Shared fields for weekly availability entries."""

    user_id: int
    week: int = Field(ge=1, le=53)
    morning_days: int = Field(default=0, ge=0, le=7)
    nighttime_days: int = Field(default=0, ge=0, le=7)
    flex_days: int = Field(default=0, ge=0, le=7)


class AvailabilityCreate(AvailabilityBase):
    """Payload for creating availability for a given user and week."""


class AvailabilityUpdate(BaseModel):
    """Partial update for availability days counts."""

    morning_days: int | None = Field(default=None, ge=0, le=7)
    nighttime_days: int | None = Field(default=None, ge=0, le=7)
    flex_days: int | None = Field(default=None, ge=0, le=7)


class AvailabilityRead(AvailabilityBase):
    """Read model for weekly availability with nested lightweight user."""

    id: int
    user: UserNameRead | None = None

    model_config = {"from_attributes": True}


class AvailabilityCompact(BaseModel):
    """Compact representation of weekly availability for a given week."""

    week: int = Field(ge=1, le=53)
    morning_days: int = Field(ge=0, le=7)
    nighttime_days: int = Field(ge=0, le=7)
    flex_days: int = Field(ge=0, le=7)


class UserAvailability(BaseModel):
    """User with display name and a list of weekly availability entries."""

    id: int
    name: str
    availability: list[AvailabilityCompact]


class AvailabilityListResponse(BaseModel):
    """Response payload for listing availability across users and weeks."""

    users: list[UserAvailability]


class AvailabilityCellUpdate(BaseModel):
    """Update a single slot value for a specific (user, year, week)."""

    slot: Literal["morning", "nighttime", "flex"]
    value: int = Field(ge=0, le=7)


class AvailabilityWeekOut(AvailabilityBase):
    """Normalized single row response for an availability week after update."""

    id: int
    model_config = {"from_attributes": True}
