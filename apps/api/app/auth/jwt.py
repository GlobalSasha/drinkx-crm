"""JWT verification.

In production: verifies Supabase-issued JWT against SUPABASE_JWT_SECRET (HS256).
In dev / before Supabase keys are wired: returns a stub user so the rest of the
pipeline is testable without external auth.

To toggle stub mode set SUPABASE_JWT_SECRET="" (default in .env.example).
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, status
from jose import JWTError, jwt

from app.config import get_settings


@dataclass(frozen=True, slots=True)
class TokenClaims:
    """Subset of JWT claims we care about."""

    sub: str          # Supabase user id (uuid)
    email: str
    name: str = ""
    is_stub: bool = False


def _is_stub_mode() -> bool:
    return not get_settings().supabase_jwt_secret


def _stub_claims() -> TokenClaims:
    """Anonymous stub identity for local dev. Always returns the same user."""
    return TokenClaims(
        sub="00000000-0000-0000-0000-000000000001",
        email="dev@drinkx.local",
        name="Dev User",
        is_stub=True,
    )


def verify_token(token: str | None) -> TokenClaims:
    """Verify a Supabase access token and return claims.

    Raises HTTPException(401) on invalid token. In stub mode falls back to
    a fixed dev identity (for local development before Supabase is configured).
    """
    if _is_stub_mode():
        return _stub_claims()

    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing token")

    s = get_settings()
    try:
        payload = jwt.decode(
            token,
            s.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except JWTError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"invalid token: {e}")

    sub = payload.get("sub")
    email = payload.get("email")
    if not sub or not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token missing sub/email")

    return TokenClaims(
        sub=str(sub),
        email=str(email),
        name=str(payload.get("user_metadata", {}).get("full_name") or payload.get("name") or ""),
    )
