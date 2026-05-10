"""0021_automation_steps: multi-step automation chains — Sprint 2.7 G2.

Revision ID: 0021_automation_steps
Revises: 0020_automations
Create Date: 2026-05-10

Approach: additive, not replacing.

Original 0020 schema kept the single `action_type` + `action_config_json`
pair on `automations`. Multi-step chains add a `steps_json` JSONB
column — when populated, it overrides the legacy single-action shape;
when null/empty, the row continues to fire as before.

Step shape:
  [
    {"type": "send_template", "config": {"template_id": "<uuid>"}},
    {"type": "delay_hours",   "config": {"hours": 24}},
    {"type": "create_task",   "config": {"title": "Follow up", "due_in_hours": 4}}
  ]

`type` ∈ {"delay_hours", "send_template", "create_task", "move_stage"}.

`automation_step_runs` is one row per *scheduled* step per fire. Step 0
fires synchronously inside `evaluate_trigger`, so its row gets
`executed_at` set immediately. Steps 1+ are picked up by the
`automation_step_scheduler` beat task every 5 min — it grabs rows
where `executed_at IS NULL AND scheduled_at <= now()`.

ADR-020: every new migration starts by widening alembic_version.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021_automation_steps"
down_revision: Union[str, None] = "0020_automations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)"
    )

    # 1. New optional column on `automations` — null/empty = legacy
    #    single-action; non-empty array = multi-step chain.
    op.add_column(
        "automations",
        sa.Column(
            "steps_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )

    # 2. Per-step audit + scheduling queue.
    op.create_table(
        "automation_step_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "automation_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("automation_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Lead snapshot at fire time. The parent run row also has it
        # (SET NULL on delete), but we duplicate here so the beat
        # scheduler can dispatch without joining four tables.
        sa.Column(
            "lead_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("leads.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # 0-indexed position in the chain.
        sa.Column("step_index", sa.Integer, nullable=False),
        # Frozen snapshot of the step config at fire time. Editing the
        # automation's `steps_json` mid-chain must NOT change the
        # behaviour of an in-flight chain — operators expect the run
        # to play out as scheduled. Store the whole {type, config}
        # object so the scheduler doesn't need to re-read the parent.
        sa.Column(
            "step_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        # When the step is allowed to run. Step 0 = parent run's
        # `executed_at` (so it's picked up immediately). Step N's
        # scheduled_at = step (N-1)'s scheduled_at + cumulative
        # `delay_hours` between them.
        sa.Column(
            "scheduled_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        # NULL = pending; populated when the scheduler dispatches it.
        sa.Column(
            "executed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        # 'pending' | 'success' | 'skipped' | 'failed'
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error", sa.String(500), nullable=True),
    )

    # Hot-path index for the beat scheduler — every 5 min it does
    #   WHERE executed_at IS NULL AND scheduled_at <= now()
    # Partial index keeps pending rows tight even if the table grows.
    op.create_index(
        "ix_automation_step_runs_pending",
        "automation_step_runs",
        ["scheduled_at"],
        postgresql_where=sa.text("executed_at IS NULL"),
    )
    # Per-parent-run lookup for the RunsDrawer per-step grid.
    op.create_index(
        "ix_automation_step_runs_parent",
        "automation_step_runs",
        ["automation_run_id", "step_index"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_automation_step_runs_parent",
        table_name="automation_step_runs",
    )
    op.drop_index(
        "ix_automation_step_runs_pending",
        table_name="automation_step_runs",
    )
    op.drop_table("automation_step_runs")
    op.drop_column("automations", "steps_json")
