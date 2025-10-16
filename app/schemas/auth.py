from __future__ import annotations

from pydantic import BaseModel


class GoogleCallbackRequest(BaseModel):
    code: str


class AuthMeResponse(BaseModel):
    """Response model for authenticated identity info."""

    sub: str
    admin: bool
