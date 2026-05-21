"""Pydantic schemas for LeadNote endpoints."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class NoteCreate(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class NoteUpdate(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class NoteOut(BaseModel):
    id: UUID
    lead_id: UUID
    text: str
    created_at: datetime
    updated_at: datetime
    author_id: UUID | None = None
    # Resolved from users; "Удалённый пользователь" when user_id is NULL.
    author_name: str
