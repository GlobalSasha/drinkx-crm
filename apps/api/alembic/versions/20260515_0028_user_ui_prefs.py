"""Add users.ui_prefs_json — per-user appearance settings.

Revision ID: 0028_user_ui_prefs
Revises: 0027_user_phone_avatar
Create Date: 2026-05-15

Adds a JSONB column to `users` holding per-user UI preferences
(sidebar color preset, page background, density, font size). Default
empty dict — the server resolves missing keys to canonical defaults
defined in `app.users.ui_prefs`, so the column starts empty and only
fills as managers customise their workspace look.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0028_user_ui_prefs"
down_revision: Union[str, None] = "0027_user_phone_avatar"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "ui_prefs_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "ui_prefs_json")
