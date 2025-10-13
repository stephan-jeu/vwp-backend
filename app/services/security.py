from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.user import User
from backend.app.services.auth_service import decode_token
from backend.db.session import get_db


_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> User:
    """Resolve the current authenticated `User` from a Bearer JWT.

    Args:
        db: Async SQLAlchemy session.
        creds: Bearer token extracted from the request.

    Returns:
        The `User` instance corresponding to the JWT subject (email).
    """

    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    try:
        claims = decode_token(creds.credentials)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    subject = claims.get("sub")
    if not subject:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    result = await db.execute(select(User).where(User.email == subject))
    user: User | None = result.scalar_one_or_none()
    if user is None:
        # No auto-registration for now
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return user


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Ensure the current user has admin privileges.

    Args:
        current_user: Injected authenticated user.

    Returns:
        The same `User` if admin is True, otherwise raises 403.
    """

    if not current_user.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return current_user


async def assert_admin(db: AsyncSession, subject_email: str) -> None:
    """Assert admin rights for the given subject in service-layer code.

    Args:
        db: Async SQLAlchemy session.
        subject_email: Email used as subject in JWT.

    Returns:
        None. Raises HTTP 403 if the user is not admin or not found.
    """

    result = await db.execute(select(User).where(User.email == subject_email))
    user: User | None = result.scalar_one_or_none()
    if user is None or not user.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
