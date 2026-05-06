"""JWT verification.

Supports both:
- Legacy HS256 (shared SUPABASE_JWT_SECRET) — used by older Supabase projects
- Modern asymmetric (ES256, RS256) via the project's JWKS endpoint at
  ${SUPABASE_URL}/auth/v1/.well-known/jwks.json — used by all new Supabase
  projects since they switched away from shared HS256 secrets.

Stub mode (ADR-014) is on while neither SUPABASE_JWT_SECRET nor SUPABASE_URL
is configured — every request returns a fixed dev identity.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status
from jose import JWTError, jwt

from app.config import get_settings


_JWKS_TTL_SECONDS = 600  # 10 min — Supabase rotates rarely
_JWKS_CACHE: dict[str, Any] = {"data": None, "fetched_at": 0.0}


@dataclass(frozen=True, slots=True)
class TokenClaims:
    """Subset of JWT claims we care about."""

    sub: str  # Supabase user id (uuid)
    email: str
    name: str = ""
    is_stub: bool = False


def _is_stub_mode() -> bool:
    s = get_settings()
    return not s.supabase_jwt_secret and not s.supabase_url


def _stub_claims() -> TokenClaims:
    return TokenClaims(
        sub="00000000-0000-0000-0000-000000000001",
        email="dev@drinkx.tech",
        name="Dev User",
        is_stub=True,
    )


def _fetch_jwks() -> dict[str, Any]:
    """Fetch the project JWKS (cached for _JWKS_TTL_SECONDS)."""
    now = time.time()
    cached = _JWKS_CACHE.get("data")
    fetched_at = _JWKS_CACHE.get("fetched_at", 0.0)
    if cached is not None and (now - fetched_at) < _JWKS_TTL_SECONDS:
        return cached  # type: ignore[no-any-return]

    s = get_settings()
    if not s.supabase_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SUPABASE_URL not configured",
        )

    url = f"{s.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310
            data = json.loads(resp.read())
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"failed to fetch JWKS: {e}",
        )

    _JWKS_CACHE["data"] = data
    _JWKS_CACHE["fetched_at"] = now
    return data


def _key_for_kid(kid: str | None) -> dict[str, Any] | None:
    """Look up a JWK by its `kid`. Returns None if unknown."""
    jwks = _fetch_jwks()
    for k in jwks.get("keys", []):
        if k.get("kid") == kid:
            return k  # type: ignore[no-any-return]
    return None


def verify_token(token: str | None) -> TokenClaims:
    """Verify a Supabase access token and return claims.

    Raises HTTPException(401) on invalid/missing token. In stub mode falls
    back to a fixed dev identity (for local development before Supabase is
    configured).
    """
    if _is_stub_mode():
        return _stub_claims()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="missing token"
        )

    # Read header (without verifying) to choose verification path
    try:
        header = jwt.get_unverified_header(token)
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"invalid token header: {e}",
        )

    alg = header.get("alg", "")
    kid = header.get("kid")
    s = get_settings()

    try:
        if alg == "HS256":
            # Legacy shared-secret path
            if not s.supabase_jwt_secret:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="HS256 token but no SUPABASE_JWT_SECRET configured",
                )
            payload = jwt.decode(
                token,
                s.supabase_jwt_secret,
                algorithms=["HS256"],
                audience="authenticated",
            )
        elif alg in ("ES256", "RS256"):
            # Asymmetric path — fetch JWK by kid from JWKS
            key = _key_for_kid(kid)
            if key is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"invalid token: no JWK matching kid={kid}",
                )
            payload = jwt.decode(
                token,
                key,
                algorithms=[alg],
                audience="authenticated",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"invalid token: unsupported alg={alg!r}",
            )
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=f"invalid token: {e}"
        )

    sub = payload.get("sub")
    email = payload.get("email")
    if not sub or not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="token missing sub/email"
        )

    return TokenClaims(
        sub=str(sub),
        email=str(email),
        name=str(
            payload.get("user_metadata", {}).get("full_name")
            or payload.get("name")
            or ""
        ),
    )
