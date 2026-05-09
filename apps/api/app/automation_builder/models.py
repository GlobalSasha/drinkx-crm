"""Automation Builder ORM — Sprint 2.5 G1."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import Base, UUIDPrimaryKeyMixin


# Discrete-string fields with service-layer guards. Codebase pattern
# (USER_ROLES, ATTRIBUTE_KINDS, VALID_CHANNELS) — no Postgres ENUM type.

VALID_TRIGGERS = ("stage_change", "form_submission", "inbox_match")
VALID_ACTIONS = ("send_template", "create_task", "move_stage")
VALID_RUN_STATUSES = ("queued", "success", "skipped", "failed")


class Automation(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "automations"
    __table_args__ = (
        Index(
            "ix_automations_workspace_trigger_active",
            "workspace_id",
            "trigger",
            "is_active",
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    trigger: Mapped[str] = mapped_column(String(40), nullable=False)
    # Per-trigger config. Shapes (documented in services.py):
    #   stage_change   → {"to_stage_id": <uuid>} (fires when lead moves to that stage; null = any)
    #   form_submission → {"form_id": <uuid>} (null = any form)
    #   inbox_match    → {} (no extra filter)
    trigger_config_json: Mapped[dict | None] = mapped_column(
        JSON, nullable=True
    )
    # Condition tree against the lead. Shape:
    #   {"all": [{"field": "priority", "op": "eq", "value": "A"}, ...]}
    #   {"any": [...]} also supported
    # Empty / null → «always fire».
    condition_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    action_type: Mapped[str] = mapped_column(String(40), nullable=False)
    # Per-action config. Shapes (documented in services.py):
    #   send_template → {"template_id": <uuid>}
    #   create_task   → {"title": str, "due_in_hours": int}
    #   move_stage    → {"target_stage_id": <uuid>}
    action_config_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
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


class AutomationRun(Base, UUIDPrimaryKeyMixin):
    """Append-only audit row per automation fire. Used by the «История»
    panel in the builder UI and by ops debugging «why didn't this run»
    retrospectively."""
    __tablename__ = "automation_runs"
    __table_args__ = (
        Index(
            "ix_automation_runs_automation_executed",
            "automation_id",
            "executed_at",
        ),
    )

    automation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("automations.id", ondelete="CASCADE"),
        nullable=False,
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("leads.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
