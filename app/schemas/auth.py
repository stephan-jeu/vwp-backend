from __future__ import annotations

from pydantic import BaseModel


class GoogleCallbackRequest(BaseModel):
    code: str
    redirect_uri: str | None = None


class MS365CallbackRequest(BaseModel):
    code: str
    redirect_uri: str | None = None


class LoginOptionResponse(BaseModel):
    provider: str  # "password", "activation_sent"
    redirect_url: str | None = None


class AuthConfigResponse(BaseModel):
    google_enabled: bool = True
    ms365_enabled: bool
    email_enabled: bool


class PasswordLoginRequest(BaseModel):
    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class AuthMeResponse(BaseModel):
    """Response model for authenticated identity info."""

    id: int
    sub: str
    full_name: str | None = None
    admin: bool
