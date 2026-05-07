"""0004_daily_plan: daily_plans, daily_plan_items, scheduled_jobs tables

Revision ID: 0004_daily_plan
Revises: 0003_enrichment_runs
Create Date: 2026-05-07
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_daily_plan"
down_revision: Union[str, None] = "0003_enrichment_runs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # daily_plans
    # -------------------------------------------------------------------------
    op.create_table(
        "daily_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
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
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("plan_date", sa.Date, nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("generation_error", sa.Text, nullable=True),
        sa.Column(
            "summary_json",
            postgresql.JSON,
            nullable=False,
            server_default=sa.text("CAST('{}' AS json)"),
        ),
        sa.UniqueConstraint("user_id", "plan_date", name="uq_daily_plans_user_date"),
    )
    op.create_index("ix_daily_plans_workspace_id", "daily_plans", ["workspace_id"])
    op.create_index("ix_daily_plans_user_id", "daily_plans", ["user_id"])
    op.create_index(
        "ix_daily_plans_user_date",
        "daily_plans",
        ["user_id", sa.text("plan_date DESC")],
    )

    # -------------------------------------------------------------------------
    # daily_plan_items
    # -------------------------------------------------------------------------
    op.create_table(
        "daily_plan_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
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
            nullable=False,
        ),
        sa.Column(
            "daily_plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("daily_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "lead_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("leads.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("priority_score", sa.Numeric(8, 2), nullable=False),
        sa.Column(
            "estimated_minutes",
            sa.Integer,
            nullable=False,
            server_default="15",
        ),
        sa.Column("time_block", sa.String(20), nullable=True),
        sa.Column(
            "task_kind",
            sa.String(30),
            nullable=False,
            server_default="call",
        ),
        sa.Column(
            "hint_one_liner",
            sa.Text,
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "done",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_daily_plan_items_daily_plan_id",
        "daily_plan_items",
        ["daily_plan_id"],
    )
    op.create_index(
        "ix_daily_plan_items_lead_id",
        "daily_plan_items",
        ["lead_id"],
    )
    op.create_index(
        "ix_dpi_plan_position",
        "daily_plan_items",
        ["daily_plan_id", "position"],
    )

    # -------------------------------------------------------------------------
    # scheduled_jobs
    # -------------------------------------------------------------------------
    op.create_table(
        "scheduled_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
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
            nullable=False,
        ),
        sa.Column("job_name", sa.String(80), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="running",
        ),
        sa.Column(
            "affected_count",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
        sa.Column("error", sa.Text, nullable=True),
    )
    op.create_index(
        "ix_scheduled_jobs_name_started",
        "scheduled_jobs",
        ["job_name", sa.text("started_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_scheduled_jobs_name_started", table_name="scheduled_jobs")
    op.drop_table("scheduled_jobs")

    op.drop_index("ix_dpi_plan_position", table_name="daily_plan_items")
    op.drop_index("ix_daily_plan_items_lead_id", table_name="daily_plan_items")
    op.drop_index("ix_daily_plan_items_daily_plan_id", table_name="daily_plan_items")
    op.drop_table("daily_plan_items")

    op.drop_index("ix_daily_plans_user_date", table_name="daily_plans")
    op.drop_index("ix_daily_plans_user_id", table_name="daily_plans")
    op.drop_index("ix_daily_plans_workspace_id", table_name="daily_plans")
    op.drop_table("daily_plans")
