"""0020_automations: Automation Builder data model — Sprint 2.5 G1.

Revision ID: 0020_automations
Revises: 0019_message_templates
Create Date: 2026-05-09

ADR-020: every new migration starts by widening
`alembic_version.version_num` to VARCHAR(255).

Two tables:
  - `automations` — the user's saved «when X happens, run Y» rule.
  - `automation_runs` — append-only audit row per fire (queued /
    success / skipped / failed).

Trigger / action shapes are stored as `String(40)` + JSON config blobs
on the same row, mirroring the codebase pattern (USER_ROLES,
ATTRIBUTE_KINDS, VALID_CHANNELS — discrete strings + service-layer
guard, no Postgres ENUM).
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020_automations"
down_revision: Union[str, None] = "0019_message_templates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)"
    )

    op.create_table(
        "automations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        # Trigger: 'stage_change' / 'form_submission' / 'inbox_match'.
        sa.Column("trigger", sa.String(40), nullable=False),
        # Trigger config — what specifically fires the rule. Shape per
        # trigger; documented in app/automation_builder/services.py.
        sa.Column("trigger_config_json", sa.JSON, nullable=True),
        # Condition tree against the lead. Shape:
        #   {"all": [{"field": "priority", "op": "eq", "value": "A"}, ...]}
        # Empty / null = «always fire».
        sa.Column("condition_json", sa.JSON, nullable=True),
        # Action: 'send_template' / 'create_task' / 'move_stage'.
        sa.Column("action_type", sa.String(40), nullable=False),
        # Action config — references template_id, due_at offset,
        # target_stage_id etc. Shape per action_type.
        sa.Column("action_config_json", sa.JSON, nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    # Hot-path index — every trigger fan-out reads (workspace_id,
    # trigger, is_active) to find candidate automations.
    op.create_index(
        "ix_automations_workspace_trigger_active",
        "automations",
        ["workspace_id", "trigger", "is_active"],
    )

    op.create_table(
        "automation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "automation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("automations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Lead the run fired against. SET NULL so the audit trail
        # outlives a deleted lead — useful for debugging «why did this
        # automation not fire today» retrospectively.
        sa.Column(
            "lead_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("leads.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(20), nullable=False),
        # Free-text reason on skipped / failed. Truncated to 500 in
        # the service before insert — keeps the run table tight.
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column(
            "executed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_automation_runs_automation_executed",
        "automation_runs",
        ["automation_id", "executed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_automation_runs_automation_executed",
        table_name="automation_runs",
    )
    op.drop_table("automation_runs")

    op.drop_index(
        "ix_automations_workspace_trigger_active",
        table_name="automations",
    )
    op.drop_table("automations")
