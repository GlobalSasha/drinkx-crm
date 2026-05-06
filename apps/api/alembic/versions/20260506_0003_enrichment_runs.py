"""0003_enrichment_runs: enrichment_runs table for Research Agent invocations

Revision ID: 0003_enrichment_runs
Revises: 0002_b2b_model
Create Date: 2026-05-06
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_enrichment_runs"
down_revision: Union[str, None] = "0002_b2b_model"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "enrichment_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "lead_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("leads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("provider", sa.String(40), nullable=True),
        sa.Column("model", sa.String(80), nullable=True),
        sa.Column("prompt_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(8, 4), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "sources_used",
            postgresql.JSON,
            nullable=False,
            server_default=sa.text("CAST('[]' AS json)"),
        ),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("result_json", postgresql.JSON, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_enrichment_runs_lead_id", "enrichment_runs", ["lead_id"])
    op.create_index("ix_enrichment_runs_status", "enrichment_runs", ["status"])
    op.create_index(
        "ix_enrichment_runs_lead_started",
        "enrichment_runs",
        ["lead_id", sa.text("started_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_enrichment_runs_lead_started", table_name="enrichment_runs")
    op.drop_index("ix_enrichment_runs_status", table_name="enrichment_runs")
    op.drop_index("ix_enrichment_runs_lead_id", table_name="enrichment_runs")
    op.drop_table("enrichment_runs")
