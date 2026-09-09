"""Add expires_at to user_invites (plan 023 — invite expiry).

Revision ID: 0057_user_invite_expires_at
Revises: 0058_task_assignee_and_standalone

Цепляется за 0058, а не за 0056: ветка «руководитель отдела продаж»
влилась в main первой (PR #171). Два потомка одного родителя дали бы
две головы Alembic, и `alembic upgrade head` при старте контейнера
остановился бы, не зная, какую ревизию применять.
Create Date: 2026-07-18
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0057_user_invite_expires_at"
down_revision: Union[str, None] = "0058_task_assignee_and_standalone"
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
