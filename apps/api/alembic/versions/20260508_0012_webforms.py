"""0012_webforms: web_forms + form_submissions for public lead capture
— Sprint 2.2 G1.

Revision ID: 0012_webforms
Revises: 0011_export_jobs
Create Date: 2026-05-08

ADR-020: every new migration starts by widening
`alembic_version.version_num` to VARCHAR(255) so long revision IDs
don't crash the upgrade. No-op when the column is already that wide.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_webforms"
down_revision: Union[str, None] = "0011_export_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ADR-020 — widen alembic_version.version_num before any DDL.
    # Idempotent in Postgres when the column is already VARCHAR(255).
    op.execute(
        "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)"
    )

    # ---- web_forms -------------------------------------------------------
    op.create_table(
        "web_forms",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("fields_json", postgresql.JSON, nullable=False),
        sa.Column(
            "target_pipeline_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("pipelines.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "target_stage_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("stages.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("redirect_url", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column(
            "submissions_count",
            sa.Integer,
            nullable=False,
            server_default="0",
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
            nullable=False,
        ),
    )
    op.create_index(
        "ix_web_forms_workspace",
        "web_forms",
        ["workspace_id", "is_active"],
    )
    # Unique-on-slug carried by the named index, not by column-level
    # unique=True — keeps the constraint name predictable for logs
    # and avoids a duplicate auto-index from the constraint.
    op.create_index(
        "ix_web_forms_slug",
        "web_forms",
        ["slug"],
        unique=True,
    )

    # ---- form_submissions ------------------------------------------------
    op.create_table(
        "form_submissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "web_form_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("web_forms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "lead_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("leads.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("raw_payload", postgresql.JSON, nullable=False),
        sa.Column("utm_json", postgresql.JSON, nullable=True),
        sa.Column("source_domain", sa.String(300), nullable=True),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_form_submissions_form",
        "form_submissions",
        ["web_form_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_form_submissions_lead",
        "form_submissions",
        ["lead_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_form_submissions_lead", table_name="form_submissions")
    op.drop_index("ix_form_submissions_form", table_name="form_submissions")
    op.drop_table("form_submissions")
    op.drop_index("ix_web_forms_slug", table_name="web_forms")
    op.drop_index("ix_web_forms_workspace", table_name="web_forms")
    op.drop_table("web_forms")
    # Don't shrink alembic_version back to VARCHAR(32) — see ADR-020.
