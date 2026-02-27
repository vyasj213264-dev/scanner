"""
Auth router — Google OAuth 2.0 flow + /auth/me endpoint.

Environment variables required:
    GOOGLE_CLIENT_ID      — from Google Cloud Console
    GOOGLE_CLIENT_SECRET  — from Google Cloud Console
    SECRET_KEY            — random string for JWT signing (generate with: openssl rand -hex 32)
    BASE_URL              — e.g. https://scanner-ub2v.onrender.com (no trailing slash)
"""
import os
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api.models.user import TokenResponse, User
from api.services.auth_service import (
    create_access_token,
    decode_access_token,
    get_or_create_user,
    get_user_by_id,
)

router = APIRouter(prefix="/auth", tags=["Auth"])
security = HTTPBearer(auto_error=False)

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"


# ---------------------------------------------------------------------------
# Dependency: get current user from Bearer token
# ---------------------------------------------------------------------------

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[User]:
    if not credentials:
        return None
    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        return None
    return get_user_by_id(user_id)


async def require_user(
    user: Optional[User] = Depends(get_current_user),
) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/google", include_in_schema=True, summary="Redirect to Google OAuth consent")
def google_login():
    """Redirect the browser to Google's OAuth 2.0 consent screen."""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=503,
            detail="Google OAuth not configured. Set GOOGLE_CLIENT_ID environment variable.",
        )
    redirect_uri = f"{BASE_URL}/auth/google/callback"
    params = (
        f"?client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope=openid%20email%20profile"
        f"&access_type=offline"
        f"&prompt=select_account"
    )
    return RedirectResponse(GOOGLE_AUTH_URL + params)


@router.get("/google/callback", include_in_schema=True, summary="Google OAuth callback")
async def google_callback(code: str, request: Request):
    """Exchange code for tokens, upsert user, return JWT via redirect."""
    redirect_uri = f"{BASE_URL}/auth/google/callback"

    async with httpx.AsyncClient() as client:
        # Exchange code for access_token
        token_resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        token_data = token_resp.json()
        if "error" in token_data:
            raise HTTPException(status_code=400, detail=token_data["error"])

        google_access_token = token_data["access_token"]

        # Get user profile from Google
        profile_resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {google_access_token}"},
        )
        profile = profile_resp.json()

    user = get_or_create_user(
        google_id=profile["id"],
        email=profile["email"],
        name=profile.get("name", ""),
        picture=profile.get("picture", ""),
    )
    jwt_token = create_access_token(user.id)

    # Redirect back to app with JWT in URL fragment (frontend picks it up)
    return RedirectResponse(f"/?token={jwt_token}")


@router.get("/me", response_model=User, summary="Get current user profile")
async def get_me(user: User = Depends(require_user)):
    """Returns the currently authenticated user's profile."""
    return user


@router.post("/logout", summary="Logout (client-side token deletion)")
async def logout():
    """Logout is handled client-side by deleting the JWT from localStorage."""
    return {"message": "Logged out"}
