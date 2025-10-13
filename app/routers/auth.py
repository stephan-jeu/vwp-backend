from __future__ import annotations

from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.core.settings import get_settings
from backend.app.services.auth_service import (
    create_access_token,
    create_refresh_token,
    decode_token,
)


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
async def login_google() -> dict[str, str]:
    """Return Google OAuth2 authorization URL to start login flow."""

    settings = get_settings()
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    return {"authorization_url": url}


@router.get("/callback")
async def oauth_callback(code: str) -> dict[str, str]:
    """Exchange Google code for tokens and issue our JWT pair.

    Args:
        code: Authorization code returned by Google.

    Returns:
        Access and refresh JWT tokens for the client.
    """

    settings = get_settings()
    token_endpoint = "https://oauth2.googleapis.com/token"
    data = {
        "code": code,
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

    # Issue our tokens, using email as subject for now
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


@router.get("/me")
async def get_me(current_sub: str = Depends(get_current_user_sub)) -> dict[str, str]:
    """Return minimal identity of the authenticated user."""

    return {"sub": current_sub}
