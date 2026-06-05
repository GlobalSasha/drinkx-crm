"""User.forms_inbox_seen_at — per-user marker for the website-leads inbox badge.

Revision ID: 0047_user_forms_inbox_seen
Revises: 0046_webform_autoreply
Create Date: 2026-06-05
"""
import sqlalchemy as sa
from alembic import op

revision = "0047_user_forms_inbox_seen"
down_revision = "0046_webform_autoreply"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("forms_inbox_seen_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "forms_inbox_seen_at")
