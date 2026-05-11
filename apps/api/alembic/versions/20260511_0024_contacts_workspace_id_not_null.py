"""0024_contacts_workspace_id_not_null — flip contacts.workspace_id to NOT NULL.

Revision ID: 0024_contacts_workspace_id_not_null
Revises: 0023_companies
Create Date: 2026-05-11

Pre-condition: `scripts/backfill_companies.py --apply` has run on prod
and `SELECT count(*) FROM contacts WHERE workspace_id IS NULL` = 0.
Auto-deploy on push will trigger this migration; operator must run the
backfill BEFORE the merge that brings 0024 to main, otherwise the
ALTER will fail.

ADR-020: widen alembic_version first.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0024_contacts_workspace_id_not_null"
down_revision: Union[str, None] = "0023_companies"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)"
    )
    # Defensive: surface the precondition violation as a clear error
    # rather than the SQLAlchemy traceback.
    op.execute(
        """
        DO $$
        DECLARE
            null_count int;
        BEGIN
            SELECT count(*) INTO null_count FROM contacts WHERE workspace_id IS NULL;
            IF null_count > 0 THEN
                RAISE EXCEPTION
                  'Cannot set contacts.workspace_id NOT NULL: % rows still have NULL. '
                  'Run scripts/backfill_companies.py --apply first.', null_count;
            END IF;
        END$$;
        """
    )
    op.alter_column("contacts", "workspace_id", nullable=False)


def downgrade() -> None:
    op.alter_column("contacts", "workspace_id", nullable=True)
