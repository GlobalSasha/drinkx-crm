"""0027_user_phone_avatar — users.phone + users.avatar_url.

Revision ID: 0027_user_phone_avatar
Revises: 0026_leads_messenger_ids
Create Date: 2026-05-12

Feature/manager-profile — adds editable profile fields for the
/settings/profile page. Name remains a single column (split on the
frontend); phone and avatar_url are new and nullable.

ADR-020: widen alembic_version first.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0027_user_phone_avatar"
down_revision: Union[str, None] = "0026_leads_messenger_ids"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)"
    )
    op.add_column("users", sa.Column("phone", sa.String(30), nullable=True))
    op.add_column("users", sa.Column("avatar_url", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "avatar_url")
    op.drop_column("users", "phone")
