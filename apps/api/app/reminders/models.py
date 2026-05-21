"""Reminder ORM model — personal sticky-notes for the Today screen.

Not lead-attached, no due date — a lightweight per-user scratchpad.
"""
from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import Base, TimestampedMixin, UUIDPrimaryKeyMixin


class Reminder(Base, UUIDPrimaryKeyMixin, TimestampedMixin):
    __tablename__ = "reminders"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    text: Mapped[str] = mapped_column(String(500), nullable=False)
