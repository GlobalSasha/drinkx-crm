"""Company country: own column next to city and address.

One nullable column, nothing existing changes. Values are copied from
linked leads separately (one-off fill, not part of this migration).

Revision ID: 0064_company_country
Revises: 0063_lead_country_address
Create Date: 2026-11-27
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0064_company_country"
down_revision: Union[str, None] = "0063_lead_country_address"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("country", sa.String(length=80), nullable=True))


def downgrade() -> None:
    op.drop_column("companies", "country")
