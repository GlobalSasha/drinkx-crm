"""Add leads.deal_brand: AeroMilk or DrinkX.

Отдельная колонка, а не замена deal_equipment: там лежит модель аппарата
(например, S400), и эти значения остаются как есть.

Revision ID: 0060_lead_deal_brand
Revises: 0059_user_lead_pool_access
Create Date: 2026-11-05
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0060_lead_deal_brand"
down_revision: Union[str, None] = "0059_user_lead_pool_access"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column("deal_brand", sa.String(20), nullable=True),
    )
    op.create_check_constraint(
        "ck_leads_deal_brand",
        "leads",
        "deal_brand IS NULL OR deal_brand IN ('AeroMilk', 'DrinkX')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_leads_deal_brand",
        "leads",
        type_="check",
    )
    op.drop_column("leads", "deal_brand")
