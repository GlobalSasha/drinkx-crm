"""Activity payload parent_task_id index — fast lookup of task attachments.

Revision ID: 0037_activity_payload_parent_task_index
Revises: 0036_base_update_tables
Create Date: 2026-05-23
"""
from alembic import op

revision = "0037_activity_payload_parent_task_index"
down_revision = "0036_base_update_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # B-tree on the JSON-extract expression. Partial-WHERE excludes non-file rows
    # so the index stays small (we expect 90%+ of activities to be comments/tasks).
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_activities_parent_task_id
        ON activities ((payload_json->>'parent_task_id'))
        WHERE type = 'file'
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_activities_parent_task_id")
