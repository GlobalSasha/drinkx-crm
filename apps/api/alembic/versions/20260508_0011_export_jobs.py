"""0011_export_jobs: bulk-export job audit + Redis-backed download — Sprint 2.1 G6.

Revision ID: 0011_export_jobs
Revises: 0010_import_jobs
Create Date: 2026-05-08

Schema only. Result bytes live in Redis under `export:{job_id}` with a
1h TTL so the download survives a few minutes of slow manager clicking
without bloating Postgres. The job row carries the redis_key so a
recovery / audit query can correlate.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_export_jobs"
down_revision: Union[str, None] = "0010_import_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "export_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # Lifecycle: pending → running → done | failed
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        # 'xlsx' | 'csv' | 'json' | 'yaml' | 'md_zip'
        sa.Column("format", sa.String(20), nullable=False),
        sa.Column("filters_json", postgresql.JSON, nullable=True),
        sa.Column("row_count", sa.Integer, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("redis_key", sa.String(200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_export_jobs_workspace",
        "export_jobs",
        ["workspace_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_export_jobs_workspace", table_name="export_jobs")
    op.drop_table("export_jobs")
