"""lead merge: merged_into_id self-FK for deduplication (Odoo merge pattern).

When duplicate leads are merged, the losers get archived_at set + merged_into_id
pointing at the surviving lead — a soft, reversible merge (vs. Odoo's hard
unlink). Self-referential FK, SET NULL.

Revision ID: 0045_lead_merged_into
Revises: 0044_utm_attribution
Create Date: 2026-06-03
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0045_lead_merged_into"
down_revision = "0044_utm_attribution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("merged_into_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_leads_merged_into", "leads", "leads", ["merged_into_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_leads_merged_into_id", "leads", ["merged_into_id"])


def downgrade() -> None:
    op.drop_index("ix_leads_merged_into_id", table_name="leads")
    op.drop_constraint("fk_leads_merged_into", "leads", type_="foreignkey")
    op.drop_column("leads", "merged_into_id")
