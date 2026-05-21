"""lead_notes table

Revision ID: 0035_lead_notes_table
Revises: 0034_reminders_table
Create Date: 2026-05-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0035_lead_notes_table"
down_revision = "0034_reminders_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lead_notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "lead_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("leads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_lead_notes_workspace_id", "lead_notes", ["workspace_id"])
    op.create_index("ix_lead_notes_lead_id", "lead_notes", ["lead_id"])


def downgrade() -> None:
    op.drop_index("ix_lead_notes_lead_id", table_name="lead_notes")
    op.drop_index("ix_lead_notes_workspace_id", table_name="lead_notes")
    op.drop_table("lead_notes")
