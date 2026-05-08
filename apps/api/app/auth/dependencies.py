"""FastAPI dependencies for protected endpoints.

Usage:
    from app.auth.dependencies import current_user

    @router.get("/something")
    async def handler(user: User = Depends(current_user)):
        ...
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.jwt import TokenClaims, verify_token
from app.auth.models import User
from app.auth.services import upsert_user_from_token
from app.db import get_db


def _extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


async def get_token_claims(
    authorization: Annotated[str | None, Header()] = None,
) -> TokenClaims:
    return verify_token(_extract_bearer(authorization))


async def current_user(
    claims: Annotated[TokenClaims, Depends(get_token_claims)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Return the active User row, creating Workspace + User on first sign-in."""
    user = await upsert_user_from_token(session, claims)
    await session.commit()
    # Refresh with workspace eager-loaded for downstream serialization
    await session.refresh(user, attribute_names=["workspace"])
    return user


async def require_admin(user: Annotated[User, Depends(current_user)]) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin role required")
    return user


async def require_admin_or_head(
    user: Annotated[User, Depends(current_user)],
) -> User:
    """Sprint 2.2: WebForms create/update/delete is gated to admin + head.
    Plain `manager` role can read but not mutate forms — same shape as
    other admin tooling (audit log, settings) but slightly looser."""
    if user.role not in ("admin", "head"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin or head role required",
        )
    return user
