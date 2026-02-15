from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Annotated

from pydantic import BaseModel, Field, ConfigDict, field_validator

# Allowed parts of day for strict availability
PartOfDay = Literal["morning", "daytime", "nighttime"]

# Mapping of day name to list of available parts
ScheduleMap = dict[str, list[PartOfDay]]


class AvailabilityPatternBase(BaseModel):
    start_date: date
    end_date: date
    max_visits_per_week: int | None = Field(default=None, ge=0)
    schedule: ScheduleMap = Field(default_factory=dict)

    @field_validator("schedule")
    @classmethod
    def validate_schedule_keys(cls, v: ScheduleMap) -> ScheduleMap:
        valid_days = {
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        }
        for day in v.keys():
            if day.lower() not in valid_days:
                raise ValueError(f"Invalid day name: {day}")
        return v

    @field_validator("end_date")
    @classmethod
    def validate_date_order(cls, v: date, info) -> date:
        if "start_date" in info.data and v < info.data["start_date"]:
            raise ValueError("end_date must be after start_date")
        return v


class AvailabilityPatternCreate(AvailabilityPatternBase):
    pass


class AvailabilityPatternUpdate(BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    max_visits_per_week: int | None = None
    schedule: ScheduleMap | None = None


class AvailabilityPatternOut(AvailabilityPatternBase):
    id: int
    user_id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
