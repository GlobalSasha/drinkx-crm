"""presence_minutes table — active working minutes per user.

Revision ID: 0055_presence_minutes
Revises: 0054_service_api_keys
Create Date: 2026-07-15
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0055_presence_minutes"
down_revision: Union[str, None] = "0054_service_api_keys"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "presence_minutes",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "minute",
            sa.DateTime(timezone=True),
            nullable=False,
            primary_key=True,
        ),
    )
    op.create_index(
        "ix_presence_minutes_ws_minute",
        "presence_minutes",
        ["workspace_id", "minute"],
    )


def downgrade() -> None:
    op.drop_index("ix_presence_minutes_ws_minute", table_name="presence_minutes")
    op.drop_table("presence_minutes")
