"""Pydantic schemas for Reminder endpoints."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ReminderCreate(BaseModel):
    text: str = Field(min_length=1, max_length=500)


class ReminderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    text: str
    created_at: datetime
