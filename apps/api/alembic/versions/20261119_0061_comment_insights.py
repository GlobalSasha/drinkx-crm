"""«Голос клиентов»: AI tags on manager comments + scan ledger.

Two new tables, nothing existing changes. Tags are written by the AI worker
through /worker/v1/insights (scope write:insights) and checked on ingest.

Revision ID: 0061_comment_insights
Revises: 0060_lead_deal_brand
Create Date: 2026-11-19
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0061_comment_insights"
down_revision: Union[str, None] = "0060_lead_deal_brand"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "comment_insights",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("workspace_id", UUID, sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("activity_id", UUID, sa.ForeignKey("activities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lead_id", UUID, sa.ForeignKey("leads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("competitor", sa.String(80), nullable=True),
        sa.Column("quote", sa.String(300), nullable=False),
        sa.Column("comment_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_comment_insights_activity_id", "comment_insights", ["activity_id"])
    op.create_index("ix_comment_insights_ws_at", "comment_insights", ["workspace_id", "comment_at"])

    op.create_table(
        "comment_insight_scans",
        sa.Column("activity_id", UUID, sa.ForeignKey("activities.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("workspace_id", UUID, sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="1"),
        sa.Column("scanned_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("comment_insight_scans")
    op.drop_index("ix_comment_insights_ws_at", table_name="comment_insights")
    op.drop_index("ix_comment_insights_activity_id", table_name="comment_insights")
    op.drop_table("comment_insights")
