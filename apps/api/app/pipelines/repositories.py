"""Pipelines data access — async SQLAlchemy 2.0."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.pipelines.models import Pipeline, Stage


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


async def get_default_first_stage(
    db: AsyncSession, workspace_id: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID] | None:
    """Find (pipeline_id, stage_id) for position-0 stage of the workspace's default pipeline.

    Returns None if no default pipeline exists or it has no stages.
    """
    result = await db.execute(
        select(Pipeline.id, Stage.id)
        .join(Stage, Stage.pipeline_id == Pipeline.id)
        .where(
            Pipeline.workspace_id == workspace_id,
            Pipeline.is_default.is_(True),
            Stage.position == 0,
        )
        .limit(1)
    )
    row = result.first()
    if row is None:
        return None
    return row[0], row[1]
