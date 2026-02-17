"""Pydantic schemas for generic activity logging entries."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.schemas.user import UserNameRead


class ActivityLogBase(BaseModel):
    """Shared fields for activity log entries.

    Args:
        actor_id: Optional id of the user who performed the action.
        action: Machine-friendly action identifier (e.g. "project_created").
        target_type: Logical type of the target entity (e.g. "project", "visit").
        target_id: Optional primary key of the target entity.
        details: Optional structured JSON payload with extra context.
        batch_id: Optional correlation id for grouping related entries.
    """

    actor_id: int | None = None
    action: str
    target_type: str
    target_id: int | None = None
    details: dict[str, Any] | None = None
    batch_id: str | None = None


class ActivityLogCreate(ActivityLogBase):
    """Payload for creating a new activity log entry."""


class ActivityLogRead(ActivityLogBase):
    """Read model for activity log entries including metadata."""

    id: int
    created_at: datetime
    actor: UserNameRead | None = None
    actors: list[UserNameRead] = []

    model_config = {"from_attributes": True}


class ActivityLogListResponse(BaseModel):
    """Paginated response with recent activity log entries.

    Args:
        items: List of activity log entries on the current page.
        total: Total number of matching activity log entries.
        page: 1-based page number of the current slice.
        page_size: Maximum number of items per page.
    """

    items: list[ActivityLogRead]
    total: int
    page: int
    page_size: int
