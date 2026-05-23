"""Quotas table — per-user revenue targets per period.

Revision ID: 0039_quotas_table
Revises: 0038_activity_archived_at
Create Date: 2026-05-23
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0039_quotas_table"
down_revision = "0038_activity_archived_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "quotas",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="RUB"),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_quotas_workspace_id", "quotas", ["workspace_id"])
    op.create_index("ix_quotas_user_id", "quotas", ["user_id"])
    # Common /forecast query is "give me quotas for workspace X within
    # period Y" — a composite index makes that one lookup, not a scan.
    op.create_index(
        "ix_quotas_workspace_period",
        "quotas",
        ["workspace_id", "period_start", "period_end"],
    )


def downgrade() -> None:
    op.drop_index("ix_quotas_workspace_period", table_name="quotas")
    op.drop_index("ix_quotas_user_id", table_name="quotas")
    op.drop_index("ix_quotas_workspace_id", table_name="quotas")
    op.drop_table("quotas")
