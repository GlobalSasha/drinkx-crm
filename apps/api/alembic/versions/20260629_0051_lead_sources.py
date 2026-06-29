"""Lead-source dictionary: per-workspace «откуда появился лид» + leads.source_id FK.

Admin-curated configurable list (Pipeline/Stage pattern), seeded with five
defaults for every existing workspace. `is_paid` flags ad channels; `is_system`
protects the two auto-attributed rows from deletion. Lead FK is nullable SET NULL.

Revision ID: 0051_lead_sources
Revises: 0050_quotes
Create Date: 2026-06-29
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0051_lead_sources"
down_revision = "0050_quotes"
branch_labels = None
depends_on = None


_DEFAULTS = (
    ("Яндекс Директ", True, True, 10),
    ("Сайт", False, True, 20),
    ("Выставка", False, False, 30),
    ("Холодный обзвон", False, False, 40),
    ("Реферал", False, False, 50),
)


def upgrade() -> None:
    op.create_table(
        "lead_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_paid", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("workspace_id", "name", name="uq_lead_sources_ws_name"),
    )
    op.create_index("ix_lead_sources_workspace_id", "lead_sources", ["workspace_id"])

    op.add_column("leads", sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_leads_source_id", "leads", "lead_sources", ["source_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_leads_source_id", "leads", ["source_id"])

    # Seed the five defaults for every existing workspace. ON CONFLICT keeps it
    # idempotent against the per-workspace unique (workspace_id, name).
    for name, is_paid, is_system, sort_order in _DEFAULTS:
        op.execute(
            sa.text(
                """
                INSERT INTO lead_sources (id, workspace_id, name, is_active, is_paid, is_system, sort_order)
                SELECT gen_random_uuid(), w.id, :name, true, :is_paid, :is_system, :sort_order
                FROM workspaces w
                ON CONFLICT (workspace_id, name) DO NOTHING
                """
            ).bindparams(name=name, is_paid=is_paid, is_system=is_system, sort_order=sort_order)
        )


def downgrade() -> None:
    op.drop_index("ix_leads_source_id", table_name="leads")
    op.drop_constraint("fk_leads_source_id", "leads", type_="foreignkey")
    op.drop_column("leads", "source_id")
    op.drop_index("ix_lead_sources_workspace_id", table_name="lead_sources")
    op.drop_table("lead_sources")
