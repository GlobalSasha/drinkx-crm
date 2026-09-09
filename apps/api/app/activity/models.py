"""Activity ORM model — polymorphic activity stream per lead."""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models import Base, TimestampedMixin, UUIDPrimaryKeyMixin


class ActivityType(str, Enum):
    comment = "comment"
    task = "task"
    reminder = "reminder"
    file = "file"
    email = "email"
    tg = "tg"
    # Sprint 3.4: voice calls — was already used in code (Mango webhook
    # writer) before being declared here.
    phone = "phone"
    system = "system"
    stage_change = "stage_change"
    score_update = "score_update"
    form_submission = "form_submission"
    # Sprint «Unified Activity Feed»: AI assistant becomes a feed
    # participant. `ai_suggestion` rows are written by the lead-agent
    # runner (background suggestion) and the /ask-chak endpoint (chat
    # answer). Body holds the suggestion text; payload_json carries
    # `action_label / action_intent / confidence`.
    ai_suggestion = "ai_suggestion"
    # System events surfaced as feed cards.
    lead_assigned = "lead_assigned"
    enrichment_done = "enrichment_done"


class Activity(Base, UUIDPrimaryKeyMixin, TimestampedMixin):
    __tablename__ = "activities"

    # Nullable since 0058: задача может жить без лида («сдать отчёт за
    # неделю»). У всех остальных типов лид есть всегда — это лента лида.
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # Рабочее пространство. Для строк с лидом остаётся пустым — его даёт
    # сам лид, и заполнять 24 места создания активностей ради этого не
    # нужно. Обязателен ровно тогда, когда лида нет (CHECK ниже).
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True
    )
    # Автор строки.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Исполнитель задачи. Пусто = «кто владеет лидом, тот и делает» —
    # так задачи вели себя до 0058, и старые строки читаются по-старому.
    assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    task_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    task_done: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    task_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reminder_trigger_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    file_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    file_kind: Mapped[str | None] = mapped_column(String(40), nullable=True)
    channel: Mapped[str | None] = mapped_column(String(20), nullable=True)
    direction: Mapped[str | None] = mapped_column(String(10), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Email-specific (Sprint 2.0 G3). gmail_message_id is the dedup guard,
    # gmail_raw_json carries the original Gmail payload (skipped if > 50KB).
    # ADR-019: emails belong to the lead card — user_id here records *which*
    # mailbox the message came from, NOT a visibility filter.
    gmail_message_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    gmail_raw_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    from_identifier: Mapped[str | None] = mapped_column(String(300), nullable=True)
    to_identifier: Mapped[str | None] = mapped_column(String(300), nullable=True)

    lead: Mapped["Lead | None"] = relationship(back_populates="activities")  # type: ignore[name-defined]

    __table_args__ = (
        sa.CheckConstraint(
            "lead_id IS NOT NULL OR workspace_id IS NOT NULL",
            name="ck_activities_scope",
        ),
        sa.Index("ix_activities_assignee_due", "assignee_user_id", "task_due_at"),
    )
