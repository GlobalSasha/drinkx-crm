"""initial: workspaces, users, pipelines, stages

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-05
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # workspaces
    op.create_table(
        "workspaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("domain", sa.String(120), unique=True, nullable=True),
        sa.Column("plan", sa.String(40), nullable=False, server_default="free"),
        sa.Column("settings_json", postgresql.JSON, nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("sprint_capacity_per_week", sa.Integer, nullable=False, server_default="20"),
    )

    # users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False, server_default=""),
        sa.Column("role", sa.String(20), nullable=False, server_default="manager"),
        sa.Column("working_hours_json", postgresql.JSON, nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("specialization", postgresql.JSON, nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("timezone", sa.String(60), nullable=False, server_default="Europe/Moscow"),
        sa.Column("max_active_deals", sa.Integer, nullable=False, server_default="20"),
        sa.Column("supabase_user_id", sa.String(64), unique=True, nullable=True),
        sa.Column("onboarding_completed", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_workspace_id", "users", ["workspace_id"])
    op.create_index("ix_users_supabase_user_id", "users", ["supabase_user_id"])

    # pipelines
    op.create_table(
        "pipelines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("type", sa.String(40), nullable=False, server_default="sales"),
        sa.Column("is_default", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.UniqueConstraint("workspace_id", "name", name="uq_pipeline_workspace_name"),
    )
    op.create_index("ix_pipelines_workspace_id", "pipelines", ["workspace_id"])

    # stages
    op.create_table(
        "stages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "pipeline_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("pipelines.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("color", sa.String(20), nullable=False, server_default="#a1a1a6"),
        sa.Column("rot_days", sa.Integer, nullable=False, server_default="7"),
        sa.Column("probability", sa.Integer, nullable=False, server_default="10"),
        sa.Column("is_won", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("is_lost", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_stages_pipeline_id", "stages", ["pipeline_id"])


def downgrade() -> None:
    op.drop_index("ix_stages_pipeline_id", table_name="stages")
    op.drop_table("stages")
    op.drop_index("ix_pipelines_workspace_id", table_name="pipelines")
    op.drop_table("pipelines")
    op.drop_index("ix_users_supabase_user_id", table_name="users")
    op.drop_index("ix_users_workspace_id", table_name="users")
    op.drop_table("users")
    op.drop_table("workspaces")
