"""WebForm auto-reply: per-form welcome email (subject + body) to the lead.

Revision ID: 0046_webform_autoreply
Revises: 0045_lead_merged_into
Create Date: 2026-06-04
"""
import sqlalchemy as sa
from alembic import op

revision = "0046_webform_autoreply"
down_revision = "0045_lead_merged_into"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "web_forms",
        sa.Column(
            "autoreply_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column(
        "web_forms",
        sa.Column("autoreply_subject", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "web_forms",
        sa.Column("autoreply_body", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("web_forms", "autoreply_body")
    op.drop_column("web_forms", "autoreply_subject")
    op.drop_column("web_forms", "autoreply_enabled")
