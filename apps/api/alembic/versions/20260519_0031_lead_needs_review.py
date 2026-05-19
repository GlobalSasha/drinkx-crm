"""lead_needs_review

Revision ID: 0031_lead_needs_review
Revises: 0030_deal_fields_and_score_details
Create Date: 2026-05-19 14:00:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
# Repo convention is slug-style identifiers (NNNN_short_topic), not the
# file's timestamp prefix. The first deploy of Sprint 3.7 failed because
# down_revision="20260516_0030" didn't match any known revision; alembic
# raised KeyError and the api container crash-looped.
revision = "0031_lead_needs_review"
down_revision = "0030_deal_fields_and_score_details"
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
