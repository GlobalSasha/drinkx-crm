"""Add expires_at to user_invites (plan 023 — invite expiry).

Revision ID: 0057_user_invite_expires_at
Revises: 0056_lead_commercial_model
Create Date: 2026-07-18
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0057_user_invite_expires_at"
down_revision: Union[str, None] = "0056_lead_commercial_model"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable: existing rows get NULL = "never expires" (no lockout of
    # in-flight invites). New invites are created with a 14-day TTL by the app.
    op.add_column(
        "user_invites",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_invites", "expires_at")
