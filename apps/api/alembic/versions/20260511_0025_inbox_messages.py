"""0025_inbox_messages — Multi-channel inbox (Telegram / MAX / Phone).

Revision ID: 0025_inbox_messages
Revises: 0024_contacts_workspace_id_not_null
Create Date: 2026-05-11

Sprint 3.4 G1 — new `inbox_messages` table for messenger and phone
channels. Gmail keeps using the existing `inbox_items` table; the
unified feed merges both at the API layer.

Includes the G4b transcript / summary / stt_provider columns up-front
so the table is not re-altered when transcription lands.

ADR-020: widen alembic_version first.
ADR-023: separate table for real-time channels instead of overloading inbox_items.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0025_inbox_messages"
down_revision: Union[str, None] = "0024_contacts_workspace_id_not_null"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)"
    )

    op.create_table(
        "inbox_messages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "lead_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("leads.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column("sender_id", sa.String(255), nullable=True),
        sa.Column("body", sa.Text, nullable=True),
        sa.Column("media_url", sa.Text, nullable=True),
        sa.Column("call_duration", sa.Integer, nullable=True),
        sa.Column("call_status", sa.String(20), nullable=True),
        sa.Column(
            "manager_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("transcript", sa.Text, nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("stt_provider", sa.String(20), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Dedup webhooks: same (channel, external_id) cannot arrive twice.
    op.execute(
        "CREATE UNIQUE INDEX uq_inbox_msg_external "
        "ON inbox_messages (channel, external_id) "
        "WHERE external_id IS NOT NULL"
    )
    op.create_index(
        "ix_inbox_msg_lead",
        "inbox_messages",
        ["lead_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_inbox_msg_sender", "inbox_messages", ["channel", "sender_id"]
    )
    op.execute(
        "CREATE INDEX ix_inbox_msg_unmatched ON inbox_messages (workspace_id) "
        "WHERE lead_id IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_inbox_msg_unmatched")
    op.drop_index("ix_inbox_msg_sender", table_name="inbox_messages")
    op.drop_index("ix_inbox_msg_lead", table_name="inbox_messages")
    op.execute("DROP INDEX IF EXISTS uq_inbox_msg_external")
    op.drop_table("inbox_messages")
