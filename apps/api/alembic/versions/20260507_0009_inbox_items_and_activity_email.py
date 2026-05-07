"""0009_inbox_items_and_activity_email: inbox_items table + activity email columns
+ widen activities.subject — Sprint 2.0 G3.

Revision ID: 0009_inbox_items_and_activity_email
Revises: 0008_channel_connections
Create Date: 2026-05-07
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_inbox_items_and_activity_email"
down_revision: Union[str, None] = "0008_channel_connections"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- activities: new email columns + widened subject -----------------
    op.add_column(
        "activities",
        sa.Column("gmail_message_id", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "activities",
        sa.Column("gmail_raw_json", postgresql.JSON, nullable=True),
    )
    op.add_column(
        "activities",
        sa.Column("from_identifier", sa.String(length=300), nullable=True),
    )
    op.add_column(
        "activities",
        sa.Column("to_identifier", sa.String(length=300), nullable=True),
    )
    op.alter_column(
        "activities",
        "subject",
        existing_type=sa.String(length=300),
        type_=sa.String(length=500),
        existing_nullable=True,
    )
    # Partial unique index: dedup guard for Gmail messages, only over rows
    # that carry a gmail_message_id (manual emails / other channels stay free).
    op.create_index(
        "ix_activities_gmail_message_id",
        "activities",
        ["gmail_message_id"],
        unique=True,
        postgresql_where=sa.text("gmail_message_id IS NOT NULL"),
    )

    # -- inbox_items ------------------------------------------------------
    op.create_table(
        "inbox_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "gmail_message_id",
            sa.String(length=200),
            nullable=False,
            unique=True,
        ),
        sa.Column("from_email", sa.String(length=300), nullable=False),
        sa.Column("to_emails", postgresql.JSON, nullable=False),
        sa.Column("subject", sa.String(length=500), nullable=True),
        sa.Column("body_preview", sa.Text, nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("suggested_action", postgresql.JSON, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_inbox_items_workspace_status",
        "inbox_items",
        ["workspace_id", "status", sa.text("received_at DESC")],
    )
    op.create_index(
        "ix_inbox_items_user_status",
        "inbox_items",
        ["user_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_inbox_items_user_status", table_name="inbox_items")
    op.drop_index("ix_inbox_items_workspace_status", table_name="inbox_items")
    op.drop_table("inbox_items")

    op.drop_index("ix_activities_gmail_message_id", table_name="activities")
    op.alter_column(
        "activities",
        "subject",
        existing_type=sa.String(length=500),
        type_=sa.String(length=300),
        existing_nullable=True,
    )
    op.drop_column("activities", "to_identifier")
    op.drop_column("activities", "from_identifier")
    op.drop_column("activities", "gmail_raw_json")
    op.drop_column("activities", "gmail_message_id")
