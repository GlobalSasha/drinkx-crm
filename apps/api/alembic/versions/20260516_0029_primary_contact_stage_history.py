"""Add leads.primary_contact_id + new lead_stage_history table.

Revision ID: 0029_primary_contact_stage_history
Revises: 0028_user_ui_prefs
Create Date: 2026-05-16

Two additive changes:

1. `leads.primary_contact_id` — nullable FK → contacts.id (SET NULL).
   Singles out one Contact per Lead as «основной ЛПР». The contacts
   table itself stays unchanged; primacy is a property of the lead,
   not the contact, so setting a new primary just rewires this FK
   without touching contact rows.

2. `lead_stage_history` — append-only audit of stage transitions.
   One open row per lead at any time (`exited_at IS NULL`). When the
   lead moves to the next stage, `stage_change.move_stage` closes
   the previous row (`exited_at = now()`, `duration_sec` computed)
   and inserts a fresh open row. The existing `activities` log of
   `type='stage_change'` stays — that's per-event detail with
   payload_json; this table is for fast «how long has this lead
   been in stage X» queries without scanning Activity payloads.

Note on FK target: spec said `pipeline_stages.id` but the actual
table is `stages` (see `app/pipelines/models.py:Stage.__tablename__`).
Using the real name here.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0029_primary_contact_stage_history"
down_revision: Union[str, None] = "0028_user_ui_prefs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. leads.primary_contact_id
    op.add_column(
        "leads",
        sa.Column(
            "primary_contact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contacts.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # 2. lead_stage_history
    op.create_table(
        "lead_stage_history",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "lead_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("leads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "stage_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("stages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "entered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "exited_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "duration_sec",
            sa.Integer(),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_lead_stage_history_lead_entered",
        "lead_stage_history",
        ["lead_id", "entered_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_lead_stage_history_lead_entered", table_name="lead_stage_history")
    op.drop_table("lead_stage_history")
    op.drop_column("leads", "primary_contact_id")
