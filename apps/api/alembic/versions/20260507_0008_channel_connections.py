"""0008_channel_connections: Gmail / Telegram OAuth + token storage — Sprint 2.0 G1.

Revision ID: 0008_channel_connections
Revises: 0007_audit_log
Create Date: 2026-05-07
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_channel_connections"
down_revision: Union[str, None] = "0007_audit_log"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "channel_connections",
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
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("channel_type", sa.String(40), nullable=False),
        # v1: stored as plaintext JSON (refresh_token + access_token + expiry).
        # SECURITY TODO Sprint 2.1: encrypt at rest with Fernet / KMS-managed key.
        sa.Column("credentials_json", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("extra_json", postgresql.JSON, nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_channel_connections_ws_type_status",
        "channel_connections",
        ["workspace_id", "channel_type", "status"],
    )
    op.create_index(
        "ix_channel_connections_user_type",
        "channel_connections",
        ["user_id", "channel_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_channel_connections_user_type", table_name="channel_connections")
    op.drop_index("ix_channel_connections_ws_type_status", table_name="channel_connections")
    op.drop_table("channel_connections")
