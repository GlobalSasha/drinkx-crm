"""Users domain Pydantic schemas — Sprint 2.4 G1."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


Role = Literal["admin", "head", "manager"]


class UserListItemOut(BaseModel):
    """Row shape for the «Команда» Settings table. Lighter than
    `UserOut` from auth/schemas.py — drops onboarding/profile noise
    that the team list doesn't need to render."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    name: str
    role: str
    last_login_at: datetime | None


class UserListOut(BaseModel):
    items: list[UserListItemOut]
    total: int


class UserInviteIn(BaseModel):
    email: EmailStr
    role: Role = "manager"


class UserInviteOut(BaseModel):
    """Returned both by `POST /invite` (fresh row) and the listing
    endpoint when a pending-invite row exists. `accepted_at` flips
    when the invitee signs in for the first time and the auth
    bootstrap inserts their User row — see services.mark_accepted."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    suggested_role: str
    invited_by_user_id: uuid.UUID | None
    created_at: datetime
    accepted_at: datetime | None


class UserRoleUpdateIn(BaseModel):
    role: Role = Field(..., description="admin / head / manager")
