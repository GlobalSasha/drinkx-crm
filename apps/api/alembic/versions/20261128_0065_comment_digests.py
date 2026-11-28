"""«Сводка за 5 дней»: table for the AI digest of manager comments.

New table only, nothing existing changes.

Revision ID: 0065_comment_digests
Revises: 0064_company_country
Create Date: 2026-11-28
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0065_comment_digests"
down_revision: Union[str, None] = "0064_company_country"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "comment_digests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("period_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_to", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sections", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_comment_digests_ws_created", "comment_digests", ["workspace_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_comment_digests_ws_created", table_name="comment_digests")
    op.drop_table("comment_digests")
