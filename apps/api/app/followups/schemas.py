"""Pydantic schemas for Followup endpoints."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class FollowupBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
    due_at: datetime | None = None
    status: str = "pending"
    reminder_kind: str = "manager"
    notes: str | None = None
    position: int = 0


class FollowupCreate(FollowupBase):
    pass


class FollowupUpdate(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str | None = None
    due_at: datetime | None = None
    status: str | None = None
    reminder_kind: str | None = None
    notes: str | None = None
    position: int | None = None


class FollowupOut(FollowupBase):
    id: UUID
    lead_id: UUID
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class FollowupsPendingOut(BaseModel):
    """Counters for the Today screen Follow-up widget.

    pending_count: status IN ('pending','active') AND due_at within the
    next 24h (includes already-overdue rows).
    overdue_count: same status filter AND due_at strictly in the past
    (subset of pending_count).
    """

    pending_count: int
    overdue_count: int
