"""Message Templates ORM — Sprint 2.4 G4."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import Base, UUIDPrimaryKeyMixin


# Allowed channel values. Plain tuple + service-layer guard, matching
# the codebase's other discrete string fields (USER_ROLES,
# ATTRIBUTE_KINDS, ChannelConnection.channel_type). Adding a new
# channel = one line + a frontend dropdown entry, no migration.
VALID_CHANNELS = ("email", "tg", "sms")


class MessageTemplate(Base, UUIDPrimaryKeyMixin):
    """Reusable message body curated by admin for Automation Builder
    (Sprint 2.5) consumption. Workspace-scoped per ADR-021."""
    __tablename__ = "message_templates"
    __table_args__ = (
        # Same name across channels (email + sms «Followup #1») is OK;
        # duplicating in the same channel is the 409.
        UniqueConstraint(
            "workspace_id",
            "name",
            "channel",
            name="uq_message_templates_workspace_name_channel",
        ),
        Index(
            "ix_message_templates_workspace_channel",
            "workspace_id",
            "channel",
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    # Optional grouping label for the admin UI («Onboarding», «Followup»).
    # Free-text — no enum, no FK; categories are just for filtering on
    # the templates list.
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    # SET NULL so a template outlives the author if their account is
    # removed — the workspace shouldn't lose curated content.
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
