from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import jwt

from backend.core.settings import get_settings


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(
    subject: str, extra_claims: Dict[str, Any] | None = None
) -> str:
    """Create a signed JWT access token for a subject (user id or email).

    Args:
        subject: The subject identifier to embed in the token.
        extra_claims: Optional additional claims to include in the token.

    Returns:
        Encoded JWT access token string.
    """

    settings = get_settings()
    expire = _now_utc() + timedelta(minutes=settings.access_token_expires_minutes)
    payload: Dict[str, Any] = {"sub": subject, "exp": expire}
    if extra_claims:
        payload.update(extra_claims)
    token = jwt.encode(
        payload,
        settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )
    return token


def create_refresh_token(subject: str) -> str:
    """Create a signed JWT refresh token.

    Args:
        subject: The subject identifier to embed in the token.

    Returns:
        Encoded JWT refresh token string.
    """

    settings = get_settings()
    expire = _now_utc() + timedelta(days=settings.refresh_token_expires_days)
    payload = {"sub": subject, "exp": expire, "typ": "refresh"}
    return jwt.encode(
        payload,
        settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def decode_token(token: str) -> Dict[str, Any]:
    """Decode and validate a JWT.

    Args:
        token: Encoded JWT token string.

    Returns:
        Decoded claims dict if valid.
    """

    settings = get_settings()
    return jwt.decode(
        token,
        settings.jwt_secret.get_secret_value(),
        algorithms=[settings.jwt_algorithm],
        options={"require": ["exp", "sub"]},
    )
