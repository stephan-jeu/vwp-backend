from __future__ import annotations

from urllib.parse import urlencode
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.settings import get_settings
from app.services.auth_service import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.schemas.auth import GoogleCallbackRequest, AuthMeResponse
from app.models.user import User
from db.session import get_db
from app.services.security import get_current_user


router = APIRouter()
security = HTTPBearer(auto_error=False)


def get_current_user_sub(
    creds: HTTPAuthorizationCredentials | None = Depends(security),
) -> str:
    """Extract and validate the current user's subject from the Bearer JWT.

    Args:
        creds: Injected HTTP Bearer credentials.

    Returns:
        The subject (`sub`) claim from the JWT.
    """

    if creds is None or not creds.scheme.lower() == "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    try:
        claims = decode_token(creds.credentials)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    sub = claims.get("sub")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return sub


@router.get("/login")
async def login_google(
    redirect_uri: Optional[str] = Query(default=None),
) -> dict[str, str]:
    """Return Google OAuth2 authorization URL to start login flow."""

    settings = get_settings()
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri or settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    return {"authorization_url": url}


@router.post("/callback")
async def oauth_callback(
    callback_request: GoogleCallbackRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Exchange Google code for tokens and issue our JWT pair.

    Args:
        callback_request: Request body containing the authorization code returned by Google.

    Returns:
        Access and refresh JWT tokens for the client.
    """

    settings = get_settings()
    token_endpoint = "https://oauth2.googleapis.com/token"
    data = {
        "code": callback_request.code,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret.get_secret_value(),
        "redirect_uri": settings.google_redirect_uri,
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(token_endpoint, data=data)
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google code"
        )
    token_payload = resp.json()

    # Optionally: validate `id_token` (Google-signed JWT). For brevity, trust email field here.
    id_token = token_payload.get("id_token")
    # In production, validate id_token's signature and claims; here we assume we get email from userinfo.

    # Fetch userinfo to obtain email
    async with httpx.AsyncClient(timeout=15) as client:
        userinfo = await client.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {token_payload.get('access_token')}"},
        )
    if userinfo.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Failed to fetch userinfo"
        )
    info = userinfo.json()
    email = info.get("email")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="No email in userinfo"
        )

    # Ensure the user exists in our database before issuing tokens
    result = await db.execute(select(User).where(User.email == email))
    db_user: User | None = result.scalar_one_or_none()
    if db_user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has no access",
        )

    # Issue our tokens, using email as subject
    access = create_access_token(subject=email)
    refresh = create_refresh_token(subject=email)
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}


@router.post("/refresh")
async def refresh_token(refresh_token: str) -> dict[str, str]:
    """Exchange a valid refresh token for a new access token."""

    try:
        claims = decode_token(refresh_token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    if claims.get("typ") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    sub = claims.get("sub")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    new_access = create_access_token(subject=sub)
    return {"access_token": new_access, "token_type": "bearer"}


@router.get("/me", response_model=AuthMeResponse)
async def get_me(current_user: User = Depends(get_current_user)) -> AuthMeResponse:
    """Return identity of the authenticated user including admin flag.

    Args:
        current_user: Injected authenticated user instance.

    Returns:
        A dictionary with the user's subject email and admin status.
    """

    return AuthMeResponse(sub=current_user.email, admin=bool(current_user.admin))
