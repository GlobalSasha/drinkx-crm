"""Pydantic schemas for Activity endpoints."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ActivityBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    type: str
    payload_json: dict = Field(default_factory=dict)
    task_due_at: datetime | None = None
    reminder_trigger_at: datetime | None = None
    file_url: str | None = None
    file_kind: str | None = None
    channel: str | None = None
    direction: str | None = None
    subject: str | None = None
    body: str | None = None


class ActivityCreate(ActivityBase):
    pass


class ActivityOut(ActivityBase):
    id: UUID
    lead_id: UUID
    user_id: UUID | None
    task_done: bool
    task_completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ActivityListOut(BaseModel):
    items: list[ActivityOut]
    next_cursor: str | None  # ISO timestamp of last item's created_at, or None when no more
