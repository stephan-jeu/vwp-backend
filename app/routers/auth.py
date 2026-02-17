from __future__ import annotations

from urllib.parse import urlencode
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.settings import get_settings
from app.services.auth_service import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
    generate_random_token,
)
from app.schemas.auth import (
    GoogleCallbackRequest,
    AuthMeResponse,
    LoginOptionResponse,
    AuthConfigResponse,
    PasswordLoginRequest,
    MS365CallbackRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
)
from app.models.user import User
from db.session import get_db
from app.services.security import get_current_user
from app.services.user_service import get_user_by_reset_token, set_user_password
from app.services.email_service import send_reset_password_email, send_activation_email
import logging
from datetime import datetime, timedelta, timezone


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


@router.get("/config", response_model=AuthConfigResponse)
async def get_auth_config() -> AuthConfigResponse:
    """Return public auth configuration (enabled providers)."""
    settings = get_settings()
    return AuthConfigResponse(
        google_enabled=True,
        ms365_enabled=settings.enable_ms365_login,
        email_enabled=settings.enable_email_login,
    )


@router.post("/login-options", response_model=LoginOptionResponse)
async def get_login_options(
    email: str = Query(..., description="User email to check account status"),
    db: AsyncSession = Depends(get_db),
) -> LoginOptionResponse:
    """Check if user is activated or needs activation email."""
    settings = get_settings()
    if not settings.enable_email_login:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email login disabled")

    result = await db.execute(select(User).where(User.email == email, User.deleted_at == None))
    user = result.scalar_one_or_none()

    if user and user.hashed_password:
        return LoginOptionResponse(provider="password")

    if user and not user.hashed_password:
        # User exists but not yet activated – send activation email
        from app.services.auth_service import generate_random_token

        token = generate_random_token()
        user.activation_token = token
        await db.commit()

        try:
            send_activation_email(user.email, token)
        except Exception as e:
            logging.error(f"Failed to send activation email: {e}")

        return LoginOptionResponse(provider="activation_sent")

    # User not found – return generic password to avoid enumeration
    return LoginOptionResponse(provider="password")


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


@router.get("/login/ms365")
async def login_ms365(
    redirect_uri: Optional[str] = Query(default=None),
) -> dict[str, str]:
    """Return MS365 OAuth2 authorization URL."""
    settings = get_settings()
    if not settings.enable_ms365_login:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MS365 login disabled")

    params = {
        "client_id": settings.ms365_client_id,
        "redirect_uri": redirect_uri or settings.ms365_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile offline_access User.Read",
        "response_mode": "query",
    }
    # Common or specific tenant
    base_url = f"https://login.microsoftonline.com/{settings.ms365_tenant_id}/oauth2/v2.0/authorize"
    url = base_url + "?" + urlencode(params)
    return {"authorization_url": url}


@router.post("/login/password")
async def login_password(
    payload: PasswordLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Login with email and password."""
    settings = get_settings()
    if not settings.enable_email_login:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Password login disabled")

    result = await db.execute(select(User).where(User.email == payload.email, User.deleted_at == None))
    user = result.scalar_one_or_none()
    
    if not user or not user.hashed_password:
        # Return generic error
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        
    if not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    access = create_access_token(subject=user.email)
    refresh = create_refresh_token(subject=user.email)
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}


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


@router.post("/callback/ms365")
async def ms365_callback(
    callback_request: MS365CallbackRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Exchange MS365 code for tokens."""
    settings = get_settings()
    
    token_endpoint = f"https://login.microsoftonline.com/{settings.ms365_tenant_id}/oauth2/v2.0/token"
    # Note: client_secret must be a string for httpx payload
    data = {
        "code": callback_request.code,
        "client_id": settings.ms365_client_id,
        "client_secret": settings.ms365_client_secret.get_secret_value(),
        "redirect_uri": settings.ms365_redirect_uri,
        "grant_type": "authorization_code",
    }
    
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(token_endpoint, data=data)
        
    if resp.status_code != 200:
        logging.error(f"MS365 Token Error: {resp.text}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid MS365 code")
        
    token_payload = resp.json()
    access_token = token_payload.get("access_token")
    
    # Get user profile from Graph API
    async with httpx.AsyncClient(timeout=15) as client:
        user_resp = await client.get(
            "https://graph.microsoft.com/v1.0/me",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        
    if user_resp.status_code != 200:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Failed to fetch MS365 profile")
        
    profile = user_resp.json()
    email = profile.get("mail") or profile.get("userPrincipalName")
    
    if not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No email found in MS365 profile")

    # Check user existence
    result = await db.execute(select(User).where(User.email == email))
    db_user = result.scalar_one_or_none()
    
    if not db_user:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User has no access")
        
    access = create_access_token(subject=email)
    refresh = create_refresh_token(subject=email)
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}


@router.post("/forgot-password")
async def forgot_password(
    payload: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """Trigger password reset flow."""
    # Always return success to avoid enumeration
    result = await db.execute(select(User).where(User.email == payload.email, User.deleted_at == None))
    user = result.scalar_one_or_none()
    
    if user:
        if user.hashed_password or user.activation_token:
            # If they have a password OR they are active (or pending activation), send reset
            # Logic: If pending activation, we might want to resend activation or send reset?
            # sending reset token is fine, it allows setting password.
            
            token = generate_random_token()
            user.reset_password_token = token
            user.reset_password_token_expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
            await db.commit()
            
            try:
                send_reset_password_email(user.email, token)
            except Exception as e:
                logging.error(f"Failed to send reset email: {e}")
                
    return {"message": "If this email exists, a password reset link has been sent."}


@router.post("/reset-password")
async def reset_password(
    payload: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """Finish password reset or activation."""
    user = await get_user_by_reset_token(db, payload.token)
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token")
        
    # Check expiry
    if user.reset_password_token == payload.token:
        # Check expiry for reset token
        if user.reset_password_token_expires_at:
            # Ensure aware datetime
            expiry = user.reset_password_token_expires_at
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            if expiry < datetime.now(timezone.utc):
                 raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Token expired")

    await set_user_password(db, user, payload.new_password)
    return {"message": "Password set successfully. You can now login."}


@router.post("/refresh")
async def refresh_token(refresh_token: str) -> dict[str, str]:
    """Exchange a valid refresh token for a new access token."""

    try:
        claims = decode_token(refresh_token)
    except Exception:
        logging.getLogger("uvicorn.error").debug(
            "Auth: refresh token decode failed", exc_info=True
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    if claims.get("typ") != "refresh":
        logging.getLogger("uvicorn.error").debug("Auth: token typ is not refresh")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    sub = claims.get("sub")
    if not sub:
        logging.getLogger("uvicorn.error").debug("Auth: refresh token missing sub")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    new_access = create_access_token(subject=sub)
    return {"access_token": new_access, "token_type": "bearer"}


@router.get("/me", response_model=AuthMeResponse)
async def get_me(current_user: User = Depends(get_current_user)) -> AuthMeResponse:
    """Return identity of the authenticated user including admin flag.

    Args:
        current_user: Injected authenticated user instance.

    Returns:
        AuthMeResponse including id, subject email, full name and admin flag.
    """

    return AuthMeResponse(
        id=current_user.id,
        sub=current_user.email,
        full_name=current_user.full_name,
        admin=bool(current_user.admin),
    )
