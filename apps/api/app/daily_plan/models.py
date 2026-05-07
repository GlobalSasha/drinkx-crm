"""Daily plan ORM models — Sprint 1.4."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Index, Integer, JSON,
    Numeric, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models import Base, TimestampedMixin, UUIDPrimaryKeyMixin


class DailyPlan(Base, UUIDPrimaryKeyMixin, TimestampedMixin):
    __tablename__ = "daily_plans"
    __table_args__ = (
        UniqueConstraint("user_id", "plan_date", name="uq_daily_plans_user_date"),
        Index("ix_daily_plans_user_date", "user_id", "plan_date"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    plan_date: Mapped[date] = mapped_column(Date, nullable=False)
    generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending", nullable=False,
    )
    generation_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    items: Mapped[list["DailyPlanItem"]] = relationship(
        back_populates="plan",
        cascade="all, delete-orphan",
        order_by="DailyPlanItem.position",
    )


class DailyPlanItem(Base, UUIDPrimaryKeyMixin, TimestampedMixin):
    __tablename__ = "daily_plan_items"
    __table_args__ = (
        Index("ix_dpi_plan_position", "daily_plan_id", "position"),
    )

    daily_plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("daily_plans.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    priority_score: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    estimated_minutes: Mapped[int] = mapped_column(
        Integer, default=15, server_default="15", nullable=False,
    )
    time_block: Mapped[str | None] = mapped_column(String(20), nullable=True)
    task_kind: Mapped[str] = mapped_column(
        String(30), default="call", server_default="call", nullable=False,
    )
    hint_one_liner: Mapped[str] = mapped_column(
        Text, default="", server_default="", nullable=False,
    )
    done: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False,
    )
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    plan: Mapped[DailyPlan] = relationship(back_populates="items")
    lead: Mapped["Lead | None"] = relationship(  # type: ignore[name-defined]
        back_populates=None, foreign_keys=[lead_id], lazy="raise",
    )


class ScheduledJob(Base, UUIDPrimaryKeyMixin, TimestampedMixin):
    __tablename__ = "scheduled_jobs"
    __table_args__ = (
        Index("ix_scheduled_jobs_name_started", "job_name", "started_at"),
    )

    job_name: Mapped[str] = mapped_column(String(80), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(20), default="running", server_default="running", nullable=False,
    )
    affected_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False,
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
