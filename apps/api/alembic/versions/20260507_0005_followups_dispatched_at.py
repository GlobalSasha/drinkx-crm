"""followups.dispatched_at — idempotency column for cron dispatcher.

Revision ID: 0005_followups_dispatched_at
Revises: 0004_daily_plan
Create Date: 2026-05-07
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0005_followups_dispatched_at"
down_revision = "0004_daily_plan"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "followups",
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("followups", "dispatched_at")
