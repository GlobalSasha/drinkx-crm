"""0010_import_jobs: bulk-import schema + audit — Sprint 2.1 G1.

Revision ID: 0010_import_jobs
Revises: 0009_inbox_items_and_activity_email
Create Date: 2026-05-08

Schema only. Credential-blob encryption (Sprint 2.0 carryover) is handled
in application code via `app/inbox/crypto.py` — Fernet tokens fit in the
existing `channel_connections.credentials_json` TEXT column with a short
prefix marker, so no migration needed there.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_import_jobs"
down_revision: Union[str, None] = "0009_inbox_items_and_activity_email"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "import_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # Lifecycle: uploaded → mapping → previewed → running → succeeded|failed|cancelled
        sa.Column("status", sa.String(20), nullable=False, server_default="uploaded"),
        # 'xlsx' | 'csv' | 'yaml' | 'json' | 'bitrix24' | 'amocrm' | 'bulk_update_yaml'
        sa.Column("format", sa.String(20), nullable=False),
        sa.Column("source_filename", sa.String(300), nullable=False, server_default=""),
        sa.Column("upload_size_bytes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_rows", sa.Integer, nullable=False, server_default="0"),
        sa.Column("processed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("succeeded", sa.Integer, nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_summary", sa.Text, nullable=True),
        # Parsed preview + column mapping + dry-run validation results.
        # Per Sprint 2.1 design decision: stored in Postgres (not Redis)
        # so previews survive worker restarts and the manager's session
        # outlasts the 1h Redis TTL we originally proposed.
        sa.Column("diff_json", postgresql.JSON, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_import_jobs_workspace_status_created",
        "import_jobs",
        ["workspace_id", "status", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_import_jobs_user_status",
        "import_jobs",
        ["user_id", "status"],
    )

    op.create_table(
        "import_errors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("import_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("row_number", sa.Integer, nullable=False),
        sa.Column("field", sa.String(60), nullable=False, server_default=""),
        sa.Column("message", sa.Text, nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_import_errors_job_row",
        "import_errors",
        ["job_id", "row_number"],
    )


def downgrade() -> None:
    op.drop_index("ix_import_errors_job_row", table_name="import_errors")
    op.drop_table("import_errors")
    op.drop_index("ix_import_jobs_user_status", table_name="import_jobs")
    op.drop_index("ix_import_jobs_workspace_status_created", table_name="import_jobs")
    op.drop_table("import_jobs")
