from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import jwt

from core.settings import get_settings


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


# --- Password & Token Utils ---

from passlib.context import CryptContext
import secrets
import string

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)


def generate_random_token(length: int = 32) -> str:
    """Generate a secure random string token."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))
