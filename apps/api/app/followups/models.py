"""Followup ORM model — task/reminder sequences per lead."""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models import Base, TimestampedMixin, UUIDPrimaryKeyMixin


class FollowupStatus(str, Enum):
    pending = "pending"
    active = "active"
    done = "done"
    overdue = "overdue"


class ReminderKind(str, Enum):
    manager = "manager"
    auto_email = "auto_email"
    ai_hint = "ai_hint"


class Followup(Base, UUIDPrimaryKeyMixin, TimestampedMixin):
    __tablename__ = "followups"

    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    reminder_kind: Mapped[str] = mapped_column(String(20), default="manager", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    lead: Mapped["Lead"] = relationship(back_populates="followups")  # type: ignore[name-defined]
