"""0017_drop_pipelines_is_default: drop the legacy `pipelines.is_default`
boolean column — Sprint 2.4 G1 housekeeping.

Revision ID: 0017_drop_pipelines_is_default
Revises: 0016_user_invites
Create Date: 2026-05-08

ADR-020: every new migration starts by widening
`alembic_version.version_num` to VARCHAR(255).

The `pipelines.is_default` boolean dates back to Sprint 1.1 — the
original «which pipeline is default» signal. Sprint 2.3 G1 moved
the canonical pointer onto `workspaces.default_pipeline_id` (FK
SET NULL) but kept the boolean for back-compat with the diff_engine
+ migration backfills.

Sprint 2.4 G1 finishes the migration:
  - Frontend `is_default` field removed from `Pipeline` type
  - Backend response shape `PipelineOut.is_default` removed
  - `diff_engine._resolve_stage_id` switched to read through
    `pipelines_repo.get_default_pipeline_id` (which itself reads
    via the FK)
  - `repositories.set_default` no longer maintains the legacy
    boolean
  - `repositories.create_pipeline` no longer sets `is_default=False`
  - `auth.services.bootstrap_workspace` no longer sets
    `is_default=True`
  - `pipelines.models.Pipeline.is_default` Mapped column removed

With every reader/writer migrated, this migration drops the column.
The data on it is redundant with `workspaces.default_pipeline_id`
so no information is lost.

Idempotent on already-dropped databases via `IF EXISTS`.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0017_drop_pipelines_is_default"
down_revision: Union[str, None] = "0016_user_invites"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)"
    )

    # IF EXISTS for idempotency — same migration applied twice (e.g.
    # a partial deploy + retry) shouldn't bomb on «column doesn't exist».
    op.execute("ALTER TABLE pipelines DROP COLUMN IF EXISTS is_default")


def downgrade() -> None:
    # Re-create the column as nullable=False with default=False so
    # existing rows can be backfilled. Also re-derive is_default=true
    # for the row pointed at by `workspaces.default_pipeline_id`.
    op.execute(
        """
        ALTER TABLE pipelines
        ADD COLUMN IF NOT EXISTS is_default BOOLEAN NOT NULL DEFAULT FALSE
        """
    )
    op.execute(
        """
        UPDATE pipelines AS p
        SET is_default = TRUE
        FROM workspaces AS w
        WHERE w.default_pipeline_id = p.id
        """
    )
