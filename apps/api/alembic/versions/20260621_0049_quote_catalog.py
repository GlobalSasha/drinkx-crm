"""Quote catalog — products table.

Revision ID: 0049_quote_catalog
Revises: 0048_lead_lookup_indexes
Create Date: 2026-06-21
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0049_quote_catalog"
down_revision = "0048_lead_lookup_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("category", sa.String(30), nullable=False, server_default="other"),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_products_workspace_active", "products", ["workspace_id", "is_active"])


def downgrade() -> None:
    op.drop_index("ix_products_workspace_active", table_name="products")
    op.drop_table("products")
