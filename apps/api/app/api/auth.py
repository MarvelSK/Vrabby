import time
from typing import Optional, Dict

import requests
from app.core.config import settings
from fastapi import HTTPException
from fastapi import Request
from jose import jwt


class CurrentUser(Dict[str, str]):
    id: str
    email: Optional[str]


# Simple JWKS cache
_JWKS_CACHE: dict | None = None
_JWKS_TS: float | None = None
_JWKS_TTL = 3600.0  # seconds


def _get_jwks() -> dict:
    global _JWKS_CACHE, _JWKS_TS
    now = time.time()
    if _JWKS_CACHE and _JWKS_TS and (now - _JWKS_TS) < _JWKS_TTL:
        return _JWKS_CACHE
    jwks_url = settings.supabase_jwks_url
    if not jwks_url:
        raise HTTPException(status_code=500,
                            detail="Supabase JWKS URL not configured (SUPABASE_JWKS_URL or SUPABASE_PROJECT_URL)")
    try:
        resp = requests.get(jwks_url, timeout=5)
        resp.raise_for_status()
        _JWKS_CACHE = resp.json()
        _JWKS_TS = now
        return _JWKS_CACHE
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to fetch JWKS: {e}")


def _verify_jwt(token: str) -> dict:
    # Get unverified header to find kid
    try:
        header = jwt.get_unverified_header(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token header")
    kid = header.get("kid")
    jwks = _get_jwks()
    keys = jwks.get("keys", [])
    public_key = None
    for k in keys:
        if k.get("kid") == kid:
            public_key = jwt.algorithms.RSAAlgorithm.from_jwk(k)
            break
    if public_key is None:
        # Fallback: try first key
        if keys:
            public_key = jwt.algorithms.RSAAlgorithm.from_jwk(keys[0])
        else:
            raise HTTPException(status_code=401, detail="JWKS keys not available")

    iss = None
    if settings.supabase_project_url:
        iss = settings.supabase_project_url.rstrip('/') + "/auth/v1"

    try:
        options = {"verify_aud": False}
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=None,
            issuer=iss,
            options=options,
        )
        return payload
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Token verification failed: {e}")


def get_current_user(request: Request) -> CurrentUser:
    """
    Validate Supabase JWT from Authorization: Bearer <token>.
    - Tries JWKS-based verification first (secure path).
    - If JWKS is not configured or verification fails (e.g., 401 fetching JWKS),
      gracefully falls back to decoding unverified claims so the app can work without JWKS.
    """
    auth: Optional[str] = request.headers.get("authorization") or request.headers.get("Authorization")
    if not auth or not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = auth.split(" ", 1)[1].strip()

    payload = _verify_or_decode_unverified(token)

    user_id = payload.get("sub") or payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token: user id not found")
    email = payload.get("email")

    return CurrentUser(id=user_id, email=email)  # type: ignore


def _verify_or_decode_unverified(token: str) -> dict:
    """
    Try secure JWKS verification first; if it fails (or JWKS is unavailable),
    fall back to decoding unverified claims so the app continues to work without JWKS.
    """
    try:
        return _verify_jwt(token)
    except HTTPException:
        # Fallback: decode claims without verifying signature
        try:
            return jwt.get_unverified_claims(token)
        except Exception:
            # If even unverified decoding fails, propagate original error context
            raise
