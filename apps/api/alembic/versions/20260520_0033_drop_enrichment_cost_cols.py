"""drop redundant cost columns from enrichment_runs

Revision ID: 0033_drop_enrichment_cost_cols
Revises: 0032_llm_usage_table
Create Date: 2026-05-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0033_drop_enrichment_cost_cols"
down_revision = "0032_llm_usage_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("enrichment_runs", "prompt_tokens")
    op.drop_column("enrichment_runs", "completion_tokens")
    op.drop_column("enrichment_runs", "cost_usd")


def downgrade() -> None:
    op.add_column("enrichment_runs",
        sa.Column("cost_usd", sa.Numeric(8, 4), nullable=False, server_default="0"))
    op.add_column("enrichment_runs",
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("enrichment_runs",
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"))
