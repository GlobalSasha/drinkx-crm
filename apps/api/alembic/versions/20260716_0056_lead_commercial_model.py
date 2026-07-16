"""Add sale/rental commercial model to leads.

Revision ID: 0056_lead_commercial_model
Revises: 0055_presence_minutes
Create Date: 2026-07-16
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0056_lead_commercial_model"
down_revision: Union[str, None] = "0055_presence_minutes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column("commercial_model", sa.String(20), nullable=True),
    )
    op.create_check_constraint(
        "ck_leads_commercial_model",
        "leads",
        "commercial_model IS NULL OR commercial_model IN ('sale', 'rental')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_leads_commercial_model",
        "leads",
        type_="check",
    )
    op.drop_column("leads", "commercial_model")
