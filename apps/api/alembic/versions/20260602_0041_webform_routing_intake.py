"""WebForm routing + intake: assignee, sla, source_label, notify_email, ingest_token.

Revision ID: 0041_webform_routing_intake
Revises: 0040_normalize_company_segments
Create Date: 2026-06-02
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0041_webform_routing_intake"
down_revision = "0040_normalize_company_segments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "web_forms",
        sa.Column("default_assignee_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_web_forms_default_assignee",
        "web_forms", "users",
        ["default_assignee_id"], ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "web_forms",
        sa.Column("contact_task_sla_hours", sa.Integer(), nullable=False, server_default="2"),
    )
    op.add_column("web_forms", sa.Column("source_label", sa.String(length=120), nullable=True))
    op.add_column("web_forms", sa.Column("notify_email", sa.String(length=254), nullable=True))
    op.add_column("web_forms", sa.Column("ingest_token", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_constraint("fk_web_forms_default_assignee", "web_forms", type_="foreignkey")
    op.drop_column("web_forms", "ingest_token")
    op.drop_column("web_forms", "notify_email")
    op.drop_column("web_forms", "source_label")
    op.drop_column("web_forms", "contact_task_sla_hours")
    op.drop_column("web_forms", "default_assignee_id")
