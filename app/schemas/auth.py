from __future__ import annotations

from pydantic import BaseModel


class GoogleCallbackRequest(BaseModel):
    code: str


class AuthMeResponse(BaseModel):
    """Response model for authenticated identity info."""

    id: int
    sub: str
    full_name: str | None = None
    admin: bool
