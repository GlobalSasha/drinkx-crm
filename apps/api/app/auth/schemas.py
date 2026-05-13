"""Pydantic DTOs for auth endpoints."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class WorkspaceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    plan: str
    sprint_capacity_per_week: int
    # Sprint 2.3 G2: surfaces the canonical default pipeline so the
    # /pipeline switcher can hydrate cold-load to the right voronka
    # without an extra round-trip.
    default_pipeline_id: uuid.UUID | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    name: str
    role: str
    timezone: str
    max_active_deals: int
    specialization: list[str]
    working_hours_json: dict[str, Any] = Field(default_factory=dict)
    onboarding_completed: bool
    last_login_at: datetime | None
    phone: str | None = None
    avatar_url: str | None = None
    created_at: datetime
    workspace: WorkspaceOut


class UserUpdateIn(BaseModel):
    """Body for PATCH /auth/me — used by Onboarding step 2 and /settings/profile."""

    name: str | None = None
    role: str | None = None
    timezone: str | None = None
    max_active_deals: int | None = Field(default=None, ge=1, le=100)
    specialization: list[str] | None = None
    working_hours_json: dict[str, Any] | None = None
    phone: str | None = None
    avatar_url: str | None = None
    mark_onboarding_complete: bool = False
