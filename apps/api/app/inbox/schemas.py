"""Inbox Pydantic schemas — Sprint 2.0 G4 + Sprint 3.4."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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


# ---------------------------------------------------------------------------
# Sprint 3.4 — messenger / phone channels (InboxMessage)
# ---------------------------------------------------------------------------

Channel = Literal["telegram", "max", "phone"]
Direction = Literal["inbound", "outbound"]


class WebhookPayload(BaseModel):
    """Normalized webhook payload, produced by `ChannelAdapter.parse_webhook`.

    Adapters convert raw provider JSON into this shape so the receive
    pipeline doesn't need to know about Telegram / MAX / Mango differences.
    Every field except `channel` / `direction` has a default — never raise
    on a missing key from the provider (Output schemas without fallback
    defaults is anti-pattern #7 in CLAUDE.md).
    """
    channel: Channel
    direction: Direction
    external_id: str | None = None
    sender_id: str | None = None
    body: str | None = None
    media_url: str | None = None
    call_duration: int | None = None
    call_status: str | None = None


class OutboundMessage(BaseModel):
    """Composer-side payload — what an adapter is asked to send."""
    channel: Channel
    recipient_id: str
    body: str
    lead_id: UUID | None = None


class InboxMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    lead_id: UUID | None
    channel: str
    direction: str
    external_id: str | None
    sender_id: str | None
    body: str | None
    media_url: str | None
    call_duration: int | None
    call_status: str | None
    transcript: str | None
    summary: str | None
    stt_provider: str | None
    created_at: datetime


class InboxFeedEntry(BaseModel):
    """A single row in the merged GET /leads/{id}/inbox response.

    `channel` = "email" → row originates from `inbox_items`.
    `channel` ∈ {telegram, max, phone} → row originates from `inbox_messages`.
    """
    id: UUID
    channel: str
    direction: str
    body: str | None = None
    subject: str | None = None              # email only
    sender_id: str | None = None            # tg chat / phone / max user
    from_email: str | None = None           # email only
    media_url: str | None = None            # phone only
    call_duration: int | None = None
    call_status: str | None = None
    transcript: str | None = None
    summary: str | None = None
    created_at: datetime


class InboxFeedChannelLink(BaseModel):
    linked: bool
    address: str | None = None
    chat_id: str | None = None
    user_id: str | None = None
    number: str | None = None


class InboxFeedOut(BaseModel):
    messages: list[InboxFeedEntry]
    channels_linked: dict[str, InboxFeedChannelLink] = Field(default_factory=dict)


class InboxUnmatchedMessagesOut(BaseModel):
    items: list[InboxMessageOut]
    total: int


class InboxMessageAssignIn(BaseModel):
    lead_id: UUID


class InboxSendIn(BaseModel):
    """POST /leads/{id}/inbox/send body.

    `channel` 'email' is reserved for G5 — until then the service
    rejects it with `channel_not_supported`.
    """
    channel: str
    body: str
    subject: str | None = None  # email only


class InboxCallIn(BaseModel):
    """POST /leads/{id}/inbox/call body — click-to-call via Mango."""
    from_extension: str


class InboxCallOut(BaseModel):
    """Mango's response after we asked it to bridge the call. Schema is
    intentionally loose — Mango echoes various fields by version."""
    status: str
    detail: dict | None = None
