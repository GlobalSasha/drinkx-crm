"""Inbox Pydantic schemas — Sprint 2.0 G4."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class InboxItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    user_id: UUID | None
    gmail_message_id: str
    from_email: str
    to_emails: list[str]
    subject: str | None
    body_preview: str | None
    received_at: datetime
    direction: str
    status: str
    suggested_action: dict[str, Any] | None
    created_at: datetime


class InboxPageOut(BaseModel):
    items: list[InboxItemOut]
    total: int
    page: int
    page_size: int


class InboxConfirmIn(BaseModel):
    """Body of POST /api/inbox/{id}/confirm."""
    action: str  # 'match_lead' | 'create_lead' | 'add_contact'
    lead_id: UUID | None = None
    company_name: str | None = None
    contact_name: str | None = None


class InboxCountOut(BaseModel):
    pending: int
