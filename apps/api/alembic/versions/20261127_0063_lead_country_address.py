"""Lead country and address: own columns next to city.

Two nullable columns, nothing existing changes. Data is moved out of
`city` separately (one-off fix, not part of this migration).

Revision ID: 0063_lead_country_address
Revises: 0062_push_subscriptions
Create Date: 2026-11-27
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0063_lead_country_address"
down_revision: Union[str, None] = "0062_push_subscriptions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("country", sa.String(length=80), nullable=True))
    op.add_column("leads", sa.Column("address", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("leads", "address")
    op.drop_column("leads", "country")
