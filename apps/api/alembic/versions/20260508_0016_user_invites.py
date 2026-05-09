"""0016_user_invites: track team invitations issued via Supabase magic-link
— Sprint 2.4 G1.

Revision ID: 0016_user_invites
Revises: 0015_merge_workspaces
Create Date: 2026-05-08

ADR-020: every new migration starts by widening
`alembic_version.version_num` to VARCHAR(255).

Sprint 2.4 G1 introduces the «Команда» section of /settings:
admins can invite team members by email, the backend hands the
invitation off to Supabase's admin API which emails a magic-link.
On first sign-in the existing `upsert_user_from_token` path runs
and the invitee joins the workspace as `manager` (per the
single-workspace model — ADR-021).

This table is the **source of truth for the admin UI**:
- Pending invites that haven't been accepted yet (no User row
  exists for them — chicken-and-egg with `users` table).
- Audit-ish trail of who invited whom, when, with what suggested
  role.
- After acceptance, `accepted_at` flips and the row stays as a
  historical breadcrumb.

The «suggested role» on the invite is informational. The actual
role is set by the inviter via `PATCH /api/users/{id}/role` AFTER
the invitee signs in (the auth bootstrap doesn't read invites —
keeps it dumb). UX: invite → wait for acceptance → admin promotes
in the same Settings table.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_user_invites"
down_revision: Union[str, None] = "0015_merge_workspaces"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)"
    )

    op.create_table(
        "user_invites",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "invited_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("suggested_role", sa.String(20), nullable=False, server_default="manager"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
    )
    # One pending invite per (workspace, email). Re-inviting after
    # acceptance is the same row — `accepted_at` flips back? No, we
    # leave the historical row alone; if a re-invite is needed after
    # the user is removed, the operator has plenty of escape hatches.
    op.create_index(
        "ix_user_invites_workspace_email",
        "user_invites",
        ["workspace_id", "email"],
        unique=True,
    )
    op.create_index(
        "ix_user_invites_email",
        "user_invites",
        ["email"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_invites_email", table_name="user_invites")
    op.drop_index("ix_user_invites_workspace_email", table_name="user_invites")
    op.drop_table("user_invites")
