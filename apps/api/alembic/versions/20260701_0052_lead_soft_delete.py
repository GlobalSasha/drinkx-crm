"""Lead soft-delete: `deleted_at` + `deleted_by` columns + workspace index.

Adds a distinct soft-delete pair to `leads` (separate from `archived_at`,
which is the enrichment-pool / merge-dedup concept). Nullable and additive —
existing rows are unaffected (all leads stay `deleted_at IS NULL`, i.e. active).

Revision ID: 0052_lead_soft_delete
Revises: 0051_lead_sources
Create Date: 2026-07-01
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0052_lead_soft_delete"
down_revision = "0051_lead_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "leads", sa.Column("deleted_by", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_leads_deleted_by", "leads", "users", ["deleted_by"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_leads_workspace_deleted_at", "leads", ["workspace_id", "deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_leads_workspace_deleted_at", table_name="leads")
    op.drop_constraint("fk_leads_deleted_by", "leads", type_="foreignkey")
    op.drop_column("leads", "deleted_by")
    op.drop_column("leads", "deleted_at")
