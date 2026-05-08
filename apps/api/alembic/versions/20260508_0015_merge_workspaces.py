"""0015_merge_workspaces: data migration — fold the legacy «Gmail»
workspace into the canonical «Drinkx» workspace.

Revision ID: 0015_merge_workspaces
Revises: 0014_bootstrap_orphan_workspaces
Create Date: 2026-05-08

ADR-020: every new migration starts by widening
`alembic_version.version_num` to VARCHAR(255).

Why this exists:

DrinkX is a single-team product. Until the hotfix in this commit
the auth bootstrap created a NEW workspace per first-time signing
user, so two team members signing in produced two disconnected
data planes — different lead pools, different pipelines, different
notifications. Two such silos existed in production:

  - 1fa8ccb3-93f1-459d-87a9-545ed0dd53e7 «Gmail»  (older, 216 leads)
  - 456610a9-d9f2-4021-a6fb-f41433233475 «Drinkx» (newer, 0 leads)

This migration folds Gmail INTO Drinkx so the team converges on a
single workspace. After the merge, the auth bootstrap (also
modified in this commit) makes every subsequent new sign-in JOIN
the existing workspace, never create a new one.

What we do:

  1. Move every lead row in Gmail to Drinkx, remapping pipeline_id +
     stage_id by stage name (both workspaces were bootstrapped from
     DEFAULT_STAGES so name-match is reliable).
  2. Move users (UPDATE workspace_id) — preserves email-uniqueness
     since each user is in exactly one workspace.
  3. Move historical workspace-scoped tables that carry user-visible
     state: audit_log, notifications, channel_connections,
     inbox_items, daily_plans, web_forms, import_jobs, export_jobs.
  4. DELETE the now-empty Gmail workspace. CASCADE drops its
     orphaned pipelines + stages (the leads have already moved to
     Drinkx's pipeline/stages, so they're not affected).

Idempotency:

  - If either workspace UUID doesn't exist on this DB (staging,
    fresh dev, prod that already merged), the migration is a no-op.
  - The DELETE at the end removes the source row, so a re-run finds
    no source and short-circuits.

Skipped intentionally:

  - scoring_criteria — workspace-scoped config not seeded on
    bootstrap, dropped on workspace delete. Whatever drinkx already
    has wins; gmail's are discarded with the cascade.
  - import_errors / form_submissions / daily_plan_items — these
    cascade through their parent rows (import_jobs / web_forms /
    daily_plans), which we move; FKs follow.

If a target row already has data with conflicting unique-key
(unlikely in practice — drinkx workspace was bootstrapped < 24h
ago and is empty), the migration aborts and the operator has to
hand-resolve. We accept this trade-off rather than silently
swallowing data.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015_merge_workspaces"
down_revision: Union[str, None] = "0014_bootstrap_orphan_workspaces"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Hardcoded UUIDs — production-specific. The migration short-circuits
# on databases that don't have these IDs (dev/staging/test).
SOURCE_WORKSPACE_ID = "1fa8ccb3-93f1-459d-87a9-545ed0dd53e7"  # «Gmail»
TARGET_WORKSPACE_ID = "456610a9-d9f2-4021-a6fb-f41433233475"  # «Drinkx»

# Tables with workspace_id FK CASCADE to workspaces. Updating these
# preserves history; otherwise the workspace DELETE at step 4 would
# cascade-purge them.
_WORKSPACE_SCOPED_TABLES = (
    "audit_log",
    "notifications",
    "channel_connections",
    "inbox_items",
    "daily_plans",
    "web_forms",
    "import_jobs",
    "export_jobs",
)


def upgrade() -> None:
    op.execute(
        "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(255)"
    )

    bind = op.get_bind()

    # Idempotency guards.
    src_exists = bind.execute(
        sa.text("SELECT 1 FROM workspaces WHERE id = :id"),
        {"id": SOURCE_WORKSPACE_ID},
    ).fetchone()
    tgt_exists = bind.execute(
        sa.text("SELECT 1 FROM workspaces WHERE id = :id"),
        {"id": TARGET_WORKSPACE_ID},
    ).fetchone()
    if src_exists is None or tgt_exists is None:
        # Production already merged, or this DB never had these IDs
        # (dev / staging / fresh test). Nothing to do.
        return

    # Resolve the target's default pipeline. 0014 will have bootstrapped
    # one for Drinkx if it was missing, and 0013 backfilled the FK from
    # is_default=true.
    row = bind.execute(
        sa.text(
            "SELECT default_pipeline_id FROM workspaces WHERE id = :id"
        ),
        {"id": TARGET_WORKSPACE_ID},
    ).fetchone()
    target_pipeline_id = row[0] if row else None

    if target_pipeline_id is None:
        # Last-ditch: pick the oldest pipeline in the target workspace.
        row = bind.execute(
            sa.text(
                """
                SELECT id FROM pipelines
                WHERE workspace_id = :id
                ORDER BY created_at ASC
                LIMIT 1
                """
            ),
            {"id": TARGET_WORKSPACE_ID},
        ).fetchone()
        if row is None:
            raise RuntimeError(
                f"Target workspace {TARGET_WORKSPACE_ID} has no pipelines — "
                "0014 should have bootstrapped one. Aborting merge to "
                "avoid orphaning leads."
            )
        target_pipeline_id = row[0]

    # Build stage-id mapping by NAME: source_stage_id → target_stage_id.
    # Both workspaces were seeded from DEFAULT_STAGES so every stage in
    # source has a name-match in target. Any non-matching source stage
    # (a custom one a manager added, unlikely on day-old Drinkx) maps
    # to NULL — the lead lands at stage_id=NULL and the manager has to
    # reassign in the UI.
    src_stages = bind.execute(
        sa.text(
            """
            SELECT s.id, s.name
            FROM stages s
            JOIN pipelines p ON s.pipeline_id = p.id
            WHERE p.workspace_id = :id
            """
        ),
        {"id": SOURCE_WORKSPACE_ID},
    ).fetchall()
    tgt_stages = bind.execute(
        sa.text("SELECT id, name FROM stages WHERE pipeline_id = :id"),
        {"id": target_pipeline_id},
    ).fetchall()
    tgt_stage_by_name = {row[1]: row[0] for row in tgt_stages}
    stage_map: dict[str, str | None] = {
        row[0]: tgt_stage_by_name.get(row[1]) for row in src_stages
    }

    # 1. Move leads with pipeline + stage remap.
    leads = bind.execute(
        sa.text(
            "SELECT id, stage_id FROM leads WHERE workspace_id = :id"
        ),
        {"id": SOURCE_WORKSPACE_ID},
    ).fetchall()

    for lead_id, src_stage_id in leads:
        new_stage_id = stage_map.get(src_stage_id) if src_stage_id else None
        bind.execute(
            sa.text(
                """
                UPDATE leads
                SET workspace_id = :tgt,
                    pipeline_id  = :pipeline,
                    stage_id     = :stage
                WHERE id = :lead_id
                """
            ),
            {
                "tgt": TARGET_WORKSPACE_ID,
                "pipeline": target_pipeline_id,
                "stage": new_stage_id,
                "lead_id": lead_id,
            },
        )

    # 2. Move users.
    bind.execute(
        sa.text(
            """
            UPDATE users SET workspace_id = :tgt
            WHERE workspace_id = :src
            """
        ),
        {"tgt": TARGET_WORKSPACE_ID, "src": SOURCE_WORKSPACE_ID},
    )

    # 3. Move workspace-scoped history tables.
    for table in _WORKSPACE_SCOPED_TABLES:
        bind.execute(
            sa.text(
                f"""
                UPDATE {table} SET workspace_id = :tgt
                WHERE workspace_id = :src
                """
            ),
            {"tgt": TARGET_WORKSPACE_ID, "src": SOURCE_WORKSPACE_ID},
        )

    # 4. Delete the now-empty source workspace. CASCADE on
    # pipelines.workspace_id drops the source's pipelines + their
    # stages — leads already moved with new pipeline/stage IDs.
    bind.execute(
        sa.text("DELETE FROM workspaces WHERE id = :src"),
        {"src": SOURCE_WORKSPACE_ID},
    )


def downgrade() -> None:
    # No-op. The merge is destructive (gmail workspace deleted, leads'
    # pipeline_id / stage_id rewritten) and we don't store provenance
    # to safely reverse. If a rollback is needed, restore from a
    # database backup.
    pass
