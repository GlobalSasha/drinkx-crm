"""Workspace-level concurrency cap for enrichment runs."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.enrichment.models import EnrichmentRun
from app.leads.models import Lead


async def count_running_for_workspace(db: AsyncSession, workspace_id: uuid.UUID) -> int:
    """Count enrichment runs currently in 'running' status for a workspace."""
    result = await db.execute(
        select(func.count(EnrichmentRun.id))
        .join(Lead, Lead.id == EnrichmentRun.lead_id)
        .where(Lead.workspace_id == workspace_id, EnrichmentRun.status == "running")
    )
    return int(result.scalar() or 0)


async def is_at_concurrency_limit(db: AsyncSession, workspace_id: uuid.UUID) -> bool:
    n = await count_running_for_workspace(db, workspace_id)
    return n >= get_settings().ai_max_parallel_jobs
