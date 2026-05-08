"""0018_custom_attributes: per-workspace user-defined fields on Lead
— Sprint 2.4 G3.

Revision ID: 0018_custom_attributes
Revises: 0017_drop_pipelines_is_default
Create Date: 2026-05-08

ADR-020: every new migration starts by widening
`alembic_version.version_num` to VARCHAR(255).

Two tables, EAV-shaped:
  - `custom_attribute_definitions` — schema (key, label, kind ∈
    text/number/date/select, options_json for select, is_required,
    position).
  - `lead_custom_values` — value per (lead, definition). Three
    polymorphic columns; the kind on the definition determines which
    column is populated.

The G3 spec ships Settings-side CRUD only; rendering values on the
LeadCard is a 2.4+ polish carryover documented in
`docs/brain/04_NEXT_SPRINT.md`.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018_custom_attributes"
down_revision: Union[str, None] = "0017_drop_pipelines_is_default"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)"
    )

    op.create_table(
        "custom_attribute_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key", sa.String(60), nullable=False),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        # JSON: list[{value: str, label: str}] for kind='select'.
        # Nullable for the other kinds.
        sa.Column("options_json", sa.JSON, nullable=True),
        sa.Column(
            "is_required",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "position",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "uq_custom_attr_def_workspace_key",
        "custom_attribute_definitions",
        ["workspace_id", "key"],
        unique=True,
    )
    op.create_index(
        "ix_custom_attr_def_workspace",
        "custom_attribute_definitions",
        ["workspace_id", "position"],
    )

    op.create_table(
        "lead_custom_values",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "lead_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("leads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "definition_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "custom_attribute_definitions.id", ondelete="CASCADE"
            ),
            nullable=False,
        ),
        # Polymorphic value columns. Service layer enforces the
        # «exactly one populated» invariant; DB-level CHECK constraint
        # would balloon the migration with no real safety win — every
        # writer goes through `app.custom_attributes.services`.
        sa.Column("value_text", sa.String, nullable=True),
        sa.Column("value_number", sa.Numeric(20, 6), nullable=True),
        sa.Column("value_date", sa.Date, nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "uq_lead_custom_value_lead_def",
        "lead_custom_values",
        ["lead_id", "definition_id"],
        unique=True,
    )
    op.create_index(
        "ix_lead_custom_values_def",
        "lead_custom_values",
        ["definition_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_lead_custom_values_def", table_name="lead_custom_values"
    )
    op.drop_index(
        "uq_lead_custom_value_lead_def", table_name="lead_custom_values"
    )
    op.drop_table("lead_custom_values")

    op.drop_index(
        "ix_custom_attr_def_workspace",
        table_name="custom_attribute_definitions",
    )
    op.drop_index(
        "uq_custom_attr_def_workspace_key",
        table_name="custom_attribute_definitions",
    )
    op.drop_table("custom_attribute_definitions")
