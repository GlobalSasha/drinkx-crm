"""Inbox ORM models — Sprint 2.0.

Currently only ChannelConnection. InboxItem + activity-level gmail_message_id
land in Group 3.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import Base, TimestampedMixin, UUIDPrimaryKeyMixin


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
