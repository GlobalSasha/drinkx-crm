"""Inbox ORM models — Sprint 2.0.

ChannelConnection: per-(workspace, user, channel_type) OAuth credentials.
InboxItem: a Gmail message with no high-confidence lead match — pending
human review (Group 3 / Group 4).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import Base, TimestampedMixin, UUIDPrimaryKeyMixin


class InboxItemStatus(str, Enum):
    pending = "pending"
    matched = "matched"
    dismissed = "dismissed"
    created_lead = "created_lead"


class EmailDirection(str, Enum):
    inbound = "inbound"
    outbound = "outbound"


class ChannelConnection(Base, UUIDPrimaryKeyMixin, TimestampedMixin):
    """OAuth / API tokens for an external messaging channel (gmail, tg, ...).

    `credentials_json` holds the raw token payload as JSON-encoded text.
    SECURITY TODO Sprint 2.1: encrypt at rest. For v1 it's stored as-is and
    accessed only by the API container.
    """
    __tablename__ = "channel_connections"
    __table_args__ = (
        Index(
            "ix_channel_connections_ws_type_status",
            "workspace_id",
            "channel_type",
            "status",
        ),
        Index(
            "ix_channel_connections_user_type",
            "user_id",
            "channel_type",
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    channel_type: Mapped[str] = mapped_column(String(40), nullable=False)
    credentials_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    extra_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class InboxItem(Base, UUIDPrimaryKeyMixin):
    """A Gmail message awaiting human review.

    Created by `app.inbox.processor.process_message` whenever the matcher
    returns confidence < 0.8 (or no match at all). The Group 4 UI lists
    pending items and exposes confirm / dismiss actions.

    `created_at` is explicit (no TimestampedMixin) per Group 3 spec — we
    don't track an updated_at on inbox_items.
    """
    __tablename__ = "inbox_items"
    __table_args__ = (
        Index(
            "ix_inbox_items_workspace_status",
            "workspace_id",
            "status",
            "received_at",
        ),
        Index("ix_inbox_items_user_status", "user_id", "status"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    gmail_message_id: Mapped[str] = mapped_column(
        String(200), nullable=False, unique=True
    )
    from_email: Mapped[str] = mapped_column(String(300), nullable=False)
    to_emails: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    body_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending", nullable=False
    )
    suggested_action: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
