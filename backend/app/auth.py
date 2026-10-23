"""Supabase token verification and role enforcement for Pizza Point APIs."""
import os
import secrets
from pathlib import Path
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

import httpx
from dotenv import load_dotenv
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

Role = Literal["customer", "kitchen", "admin"]
bearer = HTTPBearer(auto_error=False)

# Make `uvicorn app.main:app --app-dir backend` work without requiring callers
# to export variables manually. Existing environment variables take precedence.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

@dataclass
class CurrentProfile:
    id: str
    email: str
    full_name: str
    role: Role

@lru_cache
def settings() -> tuple[str, str]:
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_ANON_KEY", "")
    if not url or not key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Authentication is not configured")
    return url, key

@lru_cache
def service_settings() -> tuple[str, str]:
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Staff management is not configured")
    return url, key

def require_assistant_menu_key(
    x_assistant_menu_key: str | None = Header(default=None),
) -> None:
    """Authenticate the server-to-server menu integration without user auth."""
    expected = os.getenv("ASSISTANT_MENU_API_KEY", "")
    if not expected or not x_assistant_menu_key or not secrets.compare_digest(
        x_assistant_menu_key, expected
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid assistant menu credentials",
        )

async def get_current_profile(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> CurrentProfile:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"})
    url, anon_key = settings()
    headers = {"apikey": anon_key, "Authorization": f"Bearer {credentials.credentials}"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            user_response = await client.get(f"{url}/auth/v1/user", headers=headers)
            if user_response.status_code != 200:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token", headers={"WWW-Authenticate": "Bearer"})
            user = user_response.json()
            profile_response = await client.get(f"{url}/rest/v1/profiles", headers=headers, params={"id": f"eq.{user['id']}", "select": "id,email,full_name,role,is_active"})
            if profile_response.status_code != 200:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Profile could not be verified")
            profiles = profile_response.json()
    except httpx.HTTPError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Authentication service unavailable")
    if not profiles or not profiles[0].get("is_active") or profiles[0].get("role") not in {"customer", "kitchen", "admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="A valid application profile is required")
    profile = profiles[0]
    return CurrentProfile(id=profile["id"], email=profile["email"], full_name=profile["full_name"], role=profile["role"])

def require_roles(*allowed: Role):
    async def dependency(profile: CurrentProfile = Depends(get_current_profile)) -> CurrentProfile:
        if profile.role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return profile
    return dependency
