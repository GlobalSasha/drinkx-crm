"""Add leads.deal_amount / deal_quantity / deal_equipment / score_details_json.

Revision ID: 0030_deal_fields_and_score_details
Revises: 0029_primary_contact_stage_history
Create Date: 2026-05-16

Lead Card v2 sprint — gives the LeadCard a header strip that shows
the deal sum + equipment block and a popup that lets the manager
edit the 8 scoring criteria manually (no AI involved).

Four nullable additive columns on `leads`:

  deal_amount        NUMERIC(12,2)  — sum in rubles
  deal_quantity      INTEGER        — number of devices
  deal_equipment     VARCHAR(50)    — model code, e.g. "S100"
  score_details_json JSONB DEFAULT '{}'  — { criterion_key: 0..max_value }

`score_details_json` is the per-lead breakdown across the
workspace-configured `scoring_criteria` table (seeded 8-key default
in migration 0002). The legacy `leads.score` integer column stays —
PATCH /leads/{id}/score-details recomputes it from the JSON on every
edit, so both readers stay in sync.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0030_deal_fields_and_score_details"
down_revision: Union[str, None] = "0029_primary_contact_stage_history"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column("deal_amount", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "leads",
        sa.Column("deal_quantity", sa.Integer(), nullable=True),
    )
    op.add_column(
        "leads",
        sa.Column("deal_equipment", sa.String(50), nullable=True),
    )
    op.add_column(
        "leads",
        sa.Column(
            "score_details_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("leads", "score_details_json")
    op.drop_column("leads", "deal_equipment")
    op.drop_column("leads", "deal_quantity")
    op.drop_column("leads", "deal_amount")
