"""0023_companies — Account-layer above leads.

Revision ID: 0023_companies
Revises: 0022_lead_agent_state
Create Date: 2026-05-11

Adds the `companies` table, links `leads.company_id` and
`contacts.{workspace_id, company_id}`, enables `pg_trgm` for fuzzy
search, and lays the indexes the global-search SQL relies on.

`contacts.workspace_id` is NULLABLE here; a follow-up migration
(`0024_contacts_workspace_id_not_null`) flips it to NOT NULL after
`scripts/backfill_companies.py` runs in prod. See ADR-022 in
`docs/brain/03_DECISIONS.md`.

ADR-020: widen alembic_version first.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023_companies"
down_revision: Union[str, None] = "0022_lead_agent_state"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)"
    )

    # ------------------------------------------------------------------
    # pg_trgm — needed for the gin_trgm_ops indexes below + the
    # similarity() / % operator in global search.
    # ------------------------------------------------------------------
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # ------------------------------------------------------------------
    # companies
    # ------------------------------------------------------------------
    op.create_table(
        "companies",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("normalized_name", sa.String(255), nullable=False),
        sa.Column("legal_name", sa.String(255), nullable=True),
        sa.Column("inn", sa.String(12), nullable=True),
        sa.Column("kpp", sa.String(9), nullable=True),
        sa.Column("domain", sa.String(255), nullable=True),
        sa.Column("website", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("address", sa.Text, nullable=True),
        sa.Column("primary_segment", sa.String(50), nullable=True),
        sa.Column("employee_range", sa.String(30), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "is_archived",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
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

    # Partial unique: only active rows with an INN conflict, scoped per
    # workspace. Matches the spec's `WHERE inn IS NOT NULL AND
    # is_archived = false`.
    op.execute(
        "CREATE UNIQUE INDEX uq_companies_inn ON companies (workspace_id, inn) "
        "WHERE inn IS NOT NULL AND is_archived = false"
    )
    op.create_index("idx_companies_workspace", "companies", ["workspace_id"])
    op.create_index(
        "idx_companies_normalized", "companies", ["workspace_id", "normalized_name"]
    )
    op.execute(
        "CREATE INDEX idx_companies_name_trgm ON companies USING gin (name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX idx_companies_domain ON companies (workspace_id, domain) "
        "WHERE domain IS NOT NULL"
    )

    # ------------------------------------------------------------------
    # leads — additive
    # ------------------------------------------------------------------
    op.add_column(
        "leads",
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("idx_leads_company_id", "leads", ["company_id"])
    op.execute(
        "CREATE INDEX idx_leads_name_trgm ON leads USING gin (company_name gin_trgm_ops)"
    )

    # ------------------------------------------------------------------
    # contacts — additive. `workspace_id` is NULLABLE here; flipped to
    # NOT NULL in migration 0024 after backfill.
    # ------------------------------------------------------------------
    op.add_column(
        "contacts",
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "contacts",
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("idx_contacts_company_id", "contacts", ["company_id"])
    op.create_index("idx_contacts_workspace", "contacts", ["workspace_id"])
    op.execute(
        "CREATE INDEX idx_contacts_name_trgm ON contacts USING gin (name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX idx_contacts_email ON contacts (workspace_id, email) "
        "WHERE email IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX idx_contacts_phone ON contacts (workspace_id, phone) "
        "WHERE phone IS NOT NULL"
    )


def downgrade() -> None:
    # contacts indexes + columns
    op.execute("DROP INDEX IF EXISTS idx_contacts_phone")
    op.execute("DROP INDEX IF EXISTS idx_contacts_email")
    op.execute("DROP INDEX IF EXISTS idx_contacts_name_trgm")
    op.drop_index("idx_contacts_workspace", table_name="contacts")
    op.drop_index("idx_contacts_company_id", table_name="contacts")
    op.drop_column("contacts", "company_id")
    op.drop_column("contacts", "workspace_id")

    # leads indexes + column
    op.execute("DROP INDEX IF EXISTS idx_leads_name_trgm")
    op.drop_index("idx_leads_company_id", table_name="leads")
    op.drop_column("leads", "company_id")

    # companies indexes + table
    op.execute("DROP INDEX IF EXISTS idx_companies_domain")
    op.execute("DROP INDEX IF EXISTS idx_companies_name_trgm")
    op.drop_index("idx_companies_normalized", table_name="companies")
    op.drop_index("idx_companies_workspace", table_name="companies")
    op.execute("DROP INDEX IF EXISTS uq_companies_inn")
    op.drop_table("companies")

    # Keep pg_trgm — other extensions may use it. Drop manually if needed.
