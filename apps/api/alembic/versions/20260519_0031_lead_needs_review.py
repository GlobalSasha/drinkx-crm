"""lead_needs_review

Revision ID: 20260519_0031
Revises: 20260516_0030
Create Date: 2026-05-19 14:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "20260519_0031"
down_revision = "20260516_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column(
            "needs_review",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("leads", "needs_review")
