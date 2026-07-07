"""service_api_keys table — machine keys for external OS read access.

Revision ID: 0054_service_api_keys
Revises: 0053_automation_step_attempt_count
Create Date: 2026-07-04
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0054_service_api_keys"
down_revision: Union[str, None] = "0053_automation_step_attempt_count"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "service_api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("scopes", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_service_api_keys_key_hash", "service_api_keys", ["key_hash"], unique=True)
    op.create_index("ix_service_api_keys_workspace_id", "service_api_keys", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_service_api_keys_key_hash", table_name="service_api_keys")
    op.drop_index("ix_service_api_keys_workspace_id", table_name="service_api_keys")
    op.drop_table("service_api_keys")
