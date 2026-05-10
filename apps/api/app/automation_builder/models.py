"""Automation Builder ORM — Sprint 2.5 G1, multi-step extension Sprint 2.7 G2."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import Base, UUIDPrimaryKeyMixin


# Discrete-string fields with service-layer guards. Codebase pattern
# (USER_ROLES, ATTRIBUTE_KINDS, VALID_CHANNELS) — no Postgres ENUM type.

VALID_TRIGGERS = ("stage_change", "form_submission", "inbox_match")
VALID_ACTIONS = ("send_template", "create_task", "move_stage")
# Sprint 2.7 G2: a step's `type` is either an action OR `delay_hours`
# (gates the next step's schedule, has no side-effect of its own).
VALID_STEP_TYPES = ("delay_hours",) + VALID_ACTIONS
VALID_RUN_STATUSES = ("queued", "success", "skipped", "failed")
VALID_STEP_RUN_STATUSES = ("pending", "success", "skipped", "failed")


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
    # Sprint 2.7 G2 — multi-step chain. When present (non-empty list),
    # this overrides `action_type`/`action_config_json` and is fired
    # by `evaluate_trigger` step 0 → scheduler step 1+. Shape:
    #   [{"type": "send_template", "config": {"template_id": "<uuid>"}},
    #    {"type": "delay_hours",   "config": {"hours": 24}},
    #    {"type": "create_task",   "config": {"title": "x", "due_in_hours": 4}}]
    # Null/empty list = legacy single-action automation. Stored as
    # JSONB at the migration layer (ALTER ADD COLUMN steps_json
    # JSONB); SQLAlchemy's `JSON` type maps to JSONB on Postgres.
    steps_json: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
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


class AutomationStepRun(Base, UUIDPrimaryKeyMixin):
    """One row per scheduled step per fire — Sprint 2.7 G2.

    Step 0 is inserted by `evaluate_trigger` with `executed_at` already
    populated (synchronous fire inside the trigger SAVEPOINT). Steps
    1+ are inserted with `executed_at IS NULL` and `scheduled_at` in
    the future; the `automation_step_scheduler` beat task picks them
    up every 5 minutes.

    `step_json` is a frozen snapshot of the step's `{type, config}`
    object at fire time — editing the parent automation's `steps_json`
    must NOT change an in-flight chain's behaviour.
    """
    __tablename__ = "automation_step_runs"
    __table_args__ = (
        Index(
            "ix_automation_step_runs_pending",
            "scheduled_at",
            postgresql_where=text("executed_at IS NULL"),
        ),
        Index(
            "ix_automation_step_runs_parent",
            "automation_run_id",
            "step_index",
        ),
    )

    automation_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("automation_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("leads.id", ondelete="SET NULL"),
        nullable=True,
    )
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    step_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
