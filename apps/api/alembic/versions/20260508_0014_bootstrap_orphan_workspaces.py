"""0014_bootstrap_orphan_workspaces: ensure every workspace has at
least one pipeline + the default 12 B2B stages — hotfix.

Revision ID: 0014_bootstrap_orphan_workspaces
Revises: 0013_default_pipeline
Create Date: 2026-05-08

ADR-020: every new migration starts by widening
`alembic_version.version_num` to VARCHAR(255).

Why this exists:

A user reported on production that `/pipeline` shows no switcher
and `/leads-pool` is empty. Switcher hides itself when the
workspace has zero pipelines (PipelineSwitcher returns null on
`pipelines.length === 0`). Bootstrap_workspace is supposed to
create the first pipeline + 12 stages on every fresh sign-in,
but in this user's account that step had not produced rows by
the time they opened /pipeline. Root cause is unclear from logs;
the safest fix-forward is a defensive migration that finds any
workspace with zero pipelines and creates the canonical bootstrap
shape:

    - one Pipeline named «Новые клиенты», type=sales, is_default=true,
      position=0
    - the 12-stage B2B template (positions 0..11) verbatim from
      app/pipelines/models.py:DEFAULT_STAGES
    - workspaces.default_pipeline_id pointing at the new pipeline

The migration is idempotent at the workspace level — it only
inserts for workspaces that currently have zero rows in pipelines.
If a workspace already has a pipeline (even if the API can't see
it for some reason), the migration leaves it alone. Stages mirror
the seed in apps/api/app/pipelines/models.py exactly so a fresh
sign-in landing here vs. via bootstrap_workspace yields the same
shape.
"""
from __future__ import annotations

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014_bootstrap_orphan_workspaces"
down_revision: Union[str, None] = "0013_default_pipeline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Mirror of apps/api/app/pipelines/models.py:DEFAULT_STAGES.
# Inlined here because alembic env shouldn't import application
# code (avoids surprise side-effects on every migration run).
_DEFAULT_STAGES = [
    ("Новый контакт",      0,  "#a1a1a6", 3,  5,   False, False),
    ("Квалификация",       1,  "#0a84ff", 5,  15,  False, False),
    ("Discovery",          2,  "#5e5ce6", 7,  25,  False, False),
    ("Solution Fit",       3,  "#bf5af2", 7,  40,  False, False),
    ("Business Case / КП", 4,  "#ff9f0a", 5,  50,  False, False),
    ("Multi-stakeholder",  5,  "#ff6b00", 7,  60,  False, False),
    ("Договор / пилот",    6,  "#ff3b30", 5,  75,  False, False),
    ("Производство",       7,  "#ff2d55", 10, 85,  False, False),
    ("Пилот",              8,  "#34c759", 14, 90,  False, False),
    ("Scale / серия",      9,  "#30d158", 14, 95,  False, False),
    ("Закрыто (won)",      10, "#32d74b", 0,  100, True,  False),
    ("Закрыто (lost)",     11, "#ff3b30", 0,  0,   False, True),
]


def upgrade() -> None:
    # ADR-020 — widen alembic_version.version_num before any DDL.
    op.execute(
        "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)"
    )

    bind = op.get_bind()

    # Find every workspace that currently has zero pipelines.
    orphan_rows = bind.execute(
        sa.text(
            """
            SELECT w.id
            FROM workspaces AS w
            LEFT JOIN pipelines AS p ON p.workspace_id = w.id
            GROUP BY w.id
            HAVING COUNT(p.id) = 0
            """
        )
    ).fetchall()

    if not orphan_rows:
        # No-op for already-healthy databases.
        return

    for (workspace_id,) in orphan_rows:
        pipeline_id = uuid.uuid4()

        # 1. Insert the pipeline.
        bind.execute(
            sa.text(
                """
                INSERT INTO pipelines (
                    id, workspace_id, name, type, is_default, position,
                    created_at, updated_at
                )
                VALUES (
                    :id, :workspace_id, 'Новые клиенты', 'sales', true, 0,
                    now(), now()
                )
                """
            ),
            {"id": pipeline_id, "workspace_id": workspace_id},
        )

        # 2. Insert the 12 default stages.
        for name, position, color, rot_days, probability, is_won, is_lost in _DEFAULT_STAGES:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO stages (
                        id, pipeline_id, name, position, color,
                        rot_days, probability, is_won, is_lost,
                        gate_criteria_json, created_at, updated_at
                    )
                    VALUES (
                        :id, :pipeline_id, :name, :position, :color,
                        :rot_days, :probability, :is_won, :is_lost,
                        '[]'::json, now(), now()
                    )
                    """
                ),
                {
                    "id": uuid.uuid4(),
                    "pipeline_id": pipeline_id,
                    "name": name,
                    "position": position,
                    "color": color,
                    "rot_days": rot_days,
                    "probability": probability,
                    "is_won": is_won,
                    "is_lost": is_lost,
                },
            )

        # 3. Wire the workspace's default_pipeline_id pointer (it will
        # have been left NULL by 0013's backfill since there were no
        # pipelines to find).
        bind.execute(
            sa.text(
                """
                UPDATE workspaces
                SET default_pipeline_id = :pipeline_id
                WHERE id = :workspace_id AND default_pipeline_id IS NULL
                """
            ),
            {"pipeline_id": pipeline_id, "workspace_id": workspace_id},
        )


def downgrade() -> None:
    # No-op. The bootstrap data is indistinguishable from rows
    # created via the auth bootstrap path; we don't have enough
    # provenance to undo it safely without risking deletion of
    # legitimate user data.
    pass
