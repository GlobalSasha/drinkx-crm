"""Lead ORM model — B2B enterprise model (ADR-016)."""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models import Base, TimestampedMixin, UUIDPrimaryKeyMixin


class DealType(str, Enum):
    enterprise_direct = "enterprise_direct"
    qsr = "qsr"
    distributor_partner = "distributor_partner"
    raw_materials = "raw_materials"
    private_small = "private_small"
    service_repeat = "service_repeat"


class Priority(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"


class AssignmentStatus(str, Enum):
    pool = "pool"
    assigned = "assigned"
    transferred = "transferred"


class Lead(Base, UUIDPrimaryKeyMixin, TimestampedMixin):
    __tablename__ = "leads"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pipeline_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pipelines.id", ondelete="SET NULL"), nullable=True
    )
    stage_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stages.id", ondelete="SET NULL"), nullable=True
    )

    # Basic
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    segment: Mapped[str | None] = mapped_column(String(60), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    website: Mapped[str | None] = mapped_column(String(512), nullable=True)
    inn: Mapped[str | None] = mapped_column(String(20), nullable=True)
    source: Mapped[str | None] = mapped_column(String(60), nullable=True)
    tags_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    # B2B (ADR-004, ADR-016)
    deal_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    priority: Mapped[str | None] = mapped_column(String(2), nullable=True)
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fit_score: Mapped[float | None] = mapped_column(Numeric(4, 2), nullable=True)

    # Lead Pool (ADR-015)
    # assigned_to / transferred_from are FKs to users but have no ORM relationship —
    # loading the user is done in the service layer via a JOIN to avoid coupling the
    # leads domain to the auth domain (package-per-domain, ADR-009).
    assignment_status: Mapped[str] = mapped_column(String(20), default="pool", nullable=False)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    transferred_from: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    transferred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Rotting (ADR-010)
    next_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_rotting_stage: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_rotting_next_step: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Pilot (ADR-011)
    pilot_contract_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Lifecycle
    blocker: Mapped[str | None] = mapped_column(String(500), nullable=True)
    next_step: Mapped[str | None] = mapped_column(String(500), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    won_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lost_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lost_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ai_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Messenger identifiers (Sprint 3.4). Used to match inbound Telegram /
    # MAX webhooks back to an existing Lead before falling back to phone.
    tg_chat_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    max_user_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Lead AI Agent memory (Sprint 3.1 Phase B). Stored as JSONB at the
    # DB level — migration 0022 creates the column with `postgresql.JSONB`.
    # SQLAlchemy's plain `JSON` here maps to the same JSONB on Postgres
    # and stays compatible with the test-suite's sqlalchemy stub which
    # only exposes `JSON` / `UUID` from `sqlalchemy.dialects.postgresql`
    # (importing `JSONB` at module level breaks `test_audit.py`,
    # `test_email_sender.py`, `test_automation_*.py` collection — those
    # files predate this column). Schema of the dict is enforced by
    # Pydantic models in `app/lead_agent/schemas.py` — at the Python
    # level this is opaque.
    agent_state: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
        default=dict,
    )

    contacts: Mapped[list["Contact"]] = relationship(  # type: ignore[name-defined]
        back_populates="lead", cascade="all, delete-orphan"
    )
    activities: Mapped[list["Activity"]] = relationship(  # type: ignore[name-defined]
        back_populates="lead", cascade="all, delete-orphan"
    )
    followups: Mapped[list["Followup"]] = relationship(  # type: ignore[name-defined]
        back_populates="lead", cascade="all, delete-orphan", order_by="Followup.position"
    )

    __table_args__ = (
        sa.Index("ix_leads_workspace_stage", "workspace_id", "stage_id"),
        sa.Index("ix_leads_workspace_assignment", "workspace_id", "assignment_status"),
        sa.Index("ix_leads_rotting", "is_rotting_stage", "is_rotting_next_step"),
    )
