"""0013_default_pipeline: workspaces.default_pipeline_id FK
— Sprint 2.3 G1.

Revision ID: 0013_default_pipeline
Revises: 0012_webforms
Create Date: 2026-05-08

ADR-020: every new migration starts by widening
`alembic_version.version_num` to VARCHAR(255).

Sprint 2.3 introduces multi-pipeline support — a workspace can host
N pipelines. The previous «which one is default» signal lived on
`pipelines.is_default` (boolean). It still works as a redundant
signal but the new canonical pointer is
`workspaces.default_pipeline_id` (FK SET NULL):

  - Single source of truth — no risk of two pipelines both flagged.
  - SET NULL on the FK means deleting the last pipeline (an admin-
    only destructive op we don't expose in v1) doesn't cascade-fail.
  - Joining from workspace → default pipeline becomes a one-hop FK
    lookup, no boolean filter.

Backfill: for each workspace, set default_pipeline_id to the OLDEST
pipeline with is_default=true (the bootstrap one). Workspaces with
zero default-flagged pipelines fall back to the oldest pipeline of
any kind. Workspaces with zero pipelines get NULL — the auth
bootstrap creates one on first sign-in, this is structurally
impossible in practice but the column is nullable forever so a
manual cleanup hand-rolling rows can't hit a NOT NULL violation.

We deliberately keep `pipelines.is_default` for now — it's read by
diff_engine and by the migration's own backfill. Dropping it is a
2.4+ housekeeping pass.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_default_pipeline"
down_revision: Union[str, None] = "0012_webforms"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ADR-020 — widen alembic_version.version_num before any DDL.
    # Idempotent in Postgres when the column is already VARCHAR(255).
    op.execute(
        "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)"
    )

    # ---- column + FK ----------------------------------------------------
    op.add_column(
        "workspaces",
        sa.Column(
            "default_pipeline_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_workspaces_default_pipeline",
        source_table="workspaces",
        referent_table="pipelines",
        local_cols=["default_pipeline_id"],
        remote_cols=["id"],
        ondelete="SET NULL",
    )

    # ---- backfill -------------------------------------------------------
    # Two-pass: first prefer pipelines.is_default=true, fall back to the
    # oldest pipeline of any kind. UPDATE ... FROM (subquery) is a single
    # round-trip per pass; subquery picks the first matching pipeline per
    # workspace via DISTINCT ON.
    op.execute(
        """
        UPDATE workspaces AS w
        SET default_pipeline_id = sub.pipeline_id
        FROM (
            SELECT DISTINCT ON (workspace_id)
                workspace_id,
                id AS pipeline_id
            FROM pipelines
            WHERE is_default = true
            ORDER BY workspace_id, created_at ASC
        ) AS sub
        WHERE w.id = sub.workspace_id
          AND w.default_pipeline_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE workspaces AS w
        SET default_pipeline_id = sub.pipeline_id
        FROM (
            SELECT DISTINCT ON (workspace_id)
                workspace_id,
                id AS pipeline_id
            FROM pipelines
            ORDER BY workspace_id, created_at ASC
        ) AS sub
        WHERE w.id = sub.workspace_id
          AND w.default_pipeline_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_workspaces_default_pipeline",
        "workspaces",
        type_="foreignkey",
    )
    op.drop_column("workspaces", "default_pipeline_id")
    # Don't shrink alembic_version back to VARCHAR(32) — see ADR-020.
