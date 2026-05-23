"""Activity archived_at — soft-delete via archive instead of hard-delete.

Revision ID: 0038_activity_archived_at
Revises: 0037_activity_payload_parent_task_index
Create Date: 2026-05-23
"""
import sqlalchemy as sa
from alembic import op

revision = "0038_activity_archived_at"
down_revision = "0037_activity_payload_parent_task_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "activities",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Partial B-tree: only archived rows. Keeps the index tiny (most activities live).
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_activities_archived_at "
        "ON activities (archived_at) WHERE archived_at IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_activities_archived_at")
    op.drop_column("activities", "archived_at")
