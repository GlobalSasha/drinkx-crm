"""Auth REST endpoints."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.auth.models import User
from app.auth.schemas import UserOut, UserUpdateIn
from app.db import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=UserOut)
async def get_me(user: Annotated[User, Depends(current_user)]) -> User:
    """Returns the current user. On first call, also creates Workspace + default Pipeline."""
    return user


@router.patch("/me", response_model=UserOut)
async def update_me(
    payload: UserUpdateIn,
    user: Annotated[User, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Update profile fields (used by Onboarding step 2)."""
    if payload.name is not None:
        user.name = payload.name
    if payload.role is not None and payload.role in ("manager", "head", "admin"):
        # Only admin can promote/demote — for now any user can self-set during onboarding
        user.role = payload.role
    if payload.timezone is not None:
        user.timezone = payload.timezone
    if payload.max_active_deals is not None:
        user.max_active_deals = payload.max_active_deals
    if payload.specialization is not None:
        user.specialization = payload.specialization
    if payload.working_hours_json is not None:
        user.working_hours_json = payload.working_hours_json
    if payload.phone is not None:
        user.phone = payload.phone or None
    if payload.avatar_url is not None:
        user.avatar_url = payload.avatar_url or None
    if payload.mark_onboarding_complete:
        user.onboarding_completed = True

    await session.commit()
    await session.refresh(user, attribute_names=["workspace"])
    return user
