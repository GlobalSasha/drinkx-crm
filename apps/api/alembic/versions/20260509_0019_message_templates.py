"""0019_message_templates: workspace-scoped message templates for the
upcoming Automation Builder — Sprint 2.4 G4.

Revision ID: 0019_message_templates
Revises: 0018_custom_attributes
Create Date: 2026-05-09

ADR-020: every new migration starts by widening
`alembic_version.version_num` to VARCHAR(255).

Templates are reusable message bodies (email / tg / sms) that admins
curate in /settings → «Шаблоны». Sprint 2.5's Automation Builder will
consume them by id; G4 only ships the data model + admin CRUD UI —
no rendering / no actual outbound dispatch yet.

Schema notes:
  - `channel` is a plain VARCHAR(20) with a service-layer guard
    (VALID_CHANNELS tuple), matching the codebase's other discrete
    string fields (USER_ROLES, ATTRIBUTE_KINDS, ChannelConnection.
    channel_type). Avoids a Postgres ENUM type whose evolution would
    cost us a migration on every new channel.
  - UNIQUE (workspace_id, name, channel) — re-using the same name
    across channels (email + sms «Followup #1») is fine; duplicating
    in the SAME channel is the 409.
  - `created_by` SET NULL so a template outlives the author.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019_message_templates"
down_revision: Union[str, None] = "0018_custom_attributes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)"
    )

    op.create_table(
        "message_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
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
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "uq_message_templates_workspace_name_channel",
        "message_templates",
        ["workspace_id", "name", "channel"],
        unique=True,
    )
    op.create_index(
        "ix_message_templates_workspace_channel",
        "message_templates",
        ["workspace_id", "channel"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_message_templates_workspace_channel",
        table_name="message_templates",
    )
    op.drop_index(
        "uq_message_templates_workspace_name_channel",
        table_name="message_templates",
    )
    op.drop_table("message_templates")
