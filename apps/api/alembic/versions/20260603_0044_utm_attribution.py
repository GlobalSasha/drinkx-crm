"""UTM attribution: source/medium/campaign dictionaries + lead FKs.

Odoo `utm` module pattern. Per-workspace dictionaries with a unique name; leads
reference them so "which channel brings deals" becomes a GROUP BY. Campaigns
carry an optional owner (Odoo utm.campaign.user_id). All lead FKs nullable.

Revision ID: 0044_utm_attribution
Revises: 0043_email_dedup_keys
Create Date: 2026-06-03
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0044_utm_attribution"
down_revision = "0043_email_dedup_keys"
branch_labels = None
depends_on = None


def _dict_table(name: str, *extra_cols) -> None:
    op.create_table(
        name,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("is_auto", sa.Boolean(), nullable=False, server_default=sa.false()),
        *extra_cols,
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("workspace_id", "name", name=f"uq_{name}_ws_name"),
    )
    op.create_index(f"ix_{name}_workspace_id", name, ["workspace_id"])


def upgrade() -> None:
    _dict_table("utm_sources")
    _dict_table("utm_mediums")
    _dict_table(
        "utm_campaigns",
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
    )

    for col, target in (
        ("utm_source_id", "utm_sources"),
        ("utm_medium_id", "utm_mediums"),
        ("utm_campaign_id", "utm_campaigns"),
    ):
        op.add_column("leads", sa.Column(col, postgresql.UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(f"fk_leads_{col}", "leads", target, [col], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    for col in ("utm_source_id", "utm_medium_id", "utm_campaign_id"):
        op.drop_constraint(f"fk_leads_{col}", "leads", type_="foreignkey")
        op.drop_column("leads", col)
    for name in ("utm_campaigns", "utm_mediums", "utm_sources"):
        op.drop_index(f"ix_{name}_workspace_id", table_name=name)
        op.drop_table(name)
