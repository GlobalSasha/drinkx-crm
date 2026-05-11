"""0026_leads_messenger_ids — leads.tg_chat_id + leads.max_user_id.

Revision ID: 0026_leads_messenger_ids
Revises: 0025_inbox_messages
Create Date: 2026-05-11

Sprint 3.4 G1 — adds Telegram and MAX identifiers to leads so that
inbound messenger webhooks can match to an existing Lead by chat id.

The Sprint 3.4 spec assumed `leads.tg_chat_id` was added in Sprint 2.7
(migration 0022). It wasn't — 0022 is `lead_agent_state`. We add both
columns here in one migration.

ADR-020: widen alembic_version first.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0026_leads_messenger_ids"
down_revision: Union[str, None] = "0025_inbox_messages"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)"
    )
    op.add_column(
        "leads", sa.Column("tg_chat_id", sa.String(100), nullable=True)
    )
    op.add_column(
        "leads", sa.Column("max_user_id", sa.String(100), nullable=True)
    )
    op.execute(
        "CREATE INDEX idx_leads_tg_chat_id ON leads (workspace_id, tg_chat_id) "
        "WHERE tg_chat_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX idx_leads_max_user_id ON leads (workspace_id, max_user_id) "
        "WHERE max_user_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_leads_max_user_id")
    op.execute("DROP INDEX IF EXISTS idx_leads_tg_chat_id")
    op.drop_column("leads", "max_user_id")
    op.drop_column("leads", "tg_chat_id")
