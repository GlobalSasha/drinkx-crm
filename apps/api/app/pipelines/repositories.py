"""Pipelines data access — async SQLAlchemy 2.0.

Sprint 2.3 G1 expansion: workspace-scoped get/create/delete + the
default-pointer helpers that read through the new
`workspaces.default_pipeline_id` FK rather than the legacy
`pipelines.is_default` boolean.
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.pipelines.models import Pipeline, Stage

if TYPE_CHECKING:
    from app.auth.models import Workspace


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

async def list_for_workspace(
    db: AsyncSession, workspace_id: uuid.UUID
) -> list[Pipeline]:
    """Return all pipelines in the workspace with their stages eagerly loaded."""
    result = await db.execute(
        select(Pipeline)
        .where(Pipeline.workspace_id == workspace_id)
        .options(selectinload(Pipeline.stages))
        .order_by(Pipeline.position.asc(), Pipeline.name.asc())
    )
    return list(result.scalars().all())


async def get_by_id(
    db: AsyncSession,
    *,
    pipeline_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> Pipeline | None:
    """Workspace-scoped fetch with stages eager-loaded.

    The workspace_id filter is not optional — every caller is the admin
    routers and they ALWAYS scope by the caller's workspace. Wrong-
    workspace lookups return None (router maps to 404), they never leak
    a foreign workspace's pipeline.
    """
    result = await db.execute(
        select(Pipeline)
        .where(Pipeline.id == pipeline_id, Pipeline.workspace_id == workspace_id)
        .options(selectinload(Pipeline.stages))
    )
    return result.scalar_one_or_none()


async def stage_belongs_to_pipeline(
    db: AsyncSession,
    *,
    stage_id: uuid.UUID,
    pipeline_id: uuid.UUID,
) -> bool:
    """True iff the stage is a child of the pipeline. Used by the form
    services validation (Sprint 2.2 G4 carryover) — `target_stage_id`
    on a WebForm has to live inside `target_pipeline_id`."""
    result = await db.execute(
        select(Stage.id)
        .where(Stage.id == stage_id, Stage.pipeline_id == pipeline_id)
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def count_leads_on_pipeline(
    db: AsyncSession, *, pipeline_id: uuid.UUID
) -> int:
    """Return the number of leads currently on the pipeline. Used by
    the delete-guard in services — refuse to drop a pipeline that has
    active leads on it."""
    from app.leads.models import Lead

    result = await db.execute(
        select(func.count(Lead.id)).where(Lead.pipeline_id == pipeline_id)
    )
    return int(result.scalar_one())


async def get_default_pipeline_id(
    db: AsyncSession, *, workspace_id: uuid.UUID
) -> uuid.UUID | None:
    """Return the workspace's canonical default pipeline.

    Reads `workspaces.default_pipeline_id` first (Sprint 2.3 source of
    truth). Falls back to the legacy `pipelines.is_default=true` row
    so a workspace mid-migration (column added but backfill not yet
    run by alembic) doesn't see «no default» until alembic catches up.
    """
    from app.auth.models import Workspace

    result = await db.execute(
        select(Workspace.default_pipeline_id).where(Workspace.id == workspace_id)
    )
    pid = result.scalar_one_or_none()
    if pid is not None:
        return pid

    # Fallback path — read the legacy boolean.
    result = await db.execute(
        select(Pipeline.id)
        .where(
            Pipeline.workspace_id == workspace_id,
            Pipeline.is_default.is_(True),
        )
        .order_by(Pipeline.created_at.asc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_default_first_stage(
    db: AsyncSession, workspace_id: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID] | None:
    """Find (pipeline_id, stage_id) for position-0 stage of the
    workspace's default pipeline. Returns None if no default exists or
    it has no stages."""
    pipeline_id = await get_default_pipeline_id(db, workspace_id=workspace_id)
    if pipeline_id is None:
        return None
    result = await db.execute(
        select(Stage.id)
        .where(Stage.pipeline_id == pipeline_id, Stage.position == 0)
        .limit(1)
    )
    stage_id = result.scalar_one_or_none()
    if stage_id is None:
        return None
    return pipeline_id, stage_id


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

async def create_pipeline(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    name: str,
    type_: str,
    stages: list[dict],
) -> Pipeline:
    """Create a Pipeline + its Stage rows in the caller's session.
    Caller commits."""
    # Find the next position so a fresh pipeline lands at the end of
    # the workspace's switcher dropdown.
    result = await db.execute(
        select(func.coalesce(func.max(Pipeline.position), -1) + 1)
        .where(Pipeline.workspace_id == workspace_id)
    )
    next_position = int(result.scalar_one())

    pipeline = Pipeline(
        workspace_id=workspace_id,
        name=name[:120],
        type=type_[:40] or "sales",
        is_default=False,  # default is set explicitly via set_default
        position=next_position,
    )
    db.add(pipeline)
    await db.flush()

    for s in stages:
        db.add(Stage(pipeline_id=pipeline.id, **s))
    await db.flush()
    # Re-fetch with stages eager-loaded so the response model can
    # serialize them without an extra round-trip.
    result = await db.execute(
        select(Pipeline)
        .where(Pipeline.id == pipeline.id)
        .options(selectinload(Pipeline.stages))
    )
    return result.scalar_one()


async def rename_pipeline(
    db: AsyncSession,
    *,
    pipeline: Pipeline,
    name: str | None,
    type_: str | None,
) -> Pipeline:
    """Apply rename / type-update on the row. Stage management is
    deferred to a separate path (full replacement) — keeps this safe
    and trivial for the v1 router."""
    if name is not None:
        pipeline.name = name[:120]
    if type_ is not None:
        pipeline.type = type_[:40] or "sales"
    await db.flush()
    return pipeline


async def replace_stages(
    db: AsyncSession,
    *,
    pipeline: Pipeline,
    stages: list[dict],
) -> Pipeline:
    """Replace the pipeline's stages with the provided list. Used by
    the Settings PipelineEditor (Sprint 2.3 G3). Stage rows previously
    on the pipeline are dropped — `leads.stage_id` is ON DELETE
    SET NULL so leads stay in the pipeline but lose stage_id (manager
    has to reassign). Caller commits."""
    # Delete existing stages first (cascade-deletes any per-stage refs).
    from sqlalchemy import delete

    await db.execute(delete(Stage).where(Stage.pipeline_id == pipeline.id))
    await db.flush()
    for s in stages:
        db.add(Stage(pipeline_id=pipeline.id, **s))
    await db.flush()
    # Re-fetch with stages eager-loaded.
    result = await db.execute(
        select(Pipeline)
        .where(Pipeline.id == pipeline.id)
        .options(selectinload(Pipeline.stages))
    )
    return result.scalar_one()


async def hard_delete_pipeline(
    db: AsyncSession, *, pipeline: Pipeline
) -> None:
    """Drop the pipeline + cascade its stages. Caller is responsible
    for the «no leads on it» + «not the workspace default» guards
    (services.delete_pipeline)."""
    await db.delete(pipeline)
    await db.flush()


async def set_default(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    pipeline_id: uuid.UUID,
) -> None:
    """Flip the workspace's `default_pipeline_id` to the given pipeline
    + maintain the legacy `is_default` boolean for any reader that
    hasn't migrated to the FK yet (diff_engine, the auth bootstrap's
    initial row). Caller commits."""
    from app.auth.models import Workspace
    from sqlalchemy import update as sa_update

    # Maintain the legacy boolean across the workspace's pipelines.
    await db.execute(
        sa_update(Pipeline)
        .where(Pipeline.workspace_id == workspace_id)
        .values(is_default=False)
    )
    await db.execute(
        sa_update(Pipeline)
        .where(Pipeline.id == pipeline_id, Pipeline.workspace_id == workspace_id)
        .values(is_default=True)
    )
    # Set the canonical FK.
    await db.execute(
        sa_update(Workspace)
        .where(Workspace.id == workspace_id)
        .values(default_pipeline_id=pipeline_id)
    )
    await db.flush()
