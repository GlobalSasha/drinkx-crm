"""Enrichment service layer — workspace-scoped EnrichmentRun management."""
from __future__ import annotations

import uuid as _uuid_mod
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enrichment.models import EnrichmentRun
from app.leads.models import Lead
from app.leads.services import LeadNotFound


class EnrichmentAlreadyRunning(Exception):
    def __init__(self, run_id: UUID):
        super().__init__(f"enrichment already running: {run_id}")
        self.run_id = run_id


async def trigger_enrichment(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    user_id: UUID,
    lead_id: UUID,
) -> EnrichmentRun:
    """Create an EnrichmentRun row in 'running' status.

    Caller schedules the orchestrator via FastAPI BackgroundTasks.
    Raises LeadNotFound if lead is missing or belongs to a different workspace.
    Raises EnrichmentAlreadyRunning if there is already a 'running' run for this lead.
    """
    # Verify lead exists in this workspace
    result = await db.execute(
        select(Lead).where(Lead.id == lead_id, Lead.workspace_id == workspace_id)
    )
    lead = result.scalar_one_or_none()
    if lead is None:
        raise LeadNotFound(lead_id)

    # Rate limit: at most one in-flight run per lead
    existing = await db.execute(
        select(EnrichmentRun)
        .where(EnrichmentRun.lead_id == lead_id, EnrichmentRun.status == "running")
        .limit(1)
    )
    running_run = existing.scalar_one_or_none()
    if running_run is not None:
        raise EnrichmentAlreadyRunning(running_run.id)

    run = EnrichmentRun(
        lead_id=lead_id,
        user_id=user_id,
        status="running",
    )
    db.add(run)
    await db.flush()  # populate run.id without committing
    return run


async def get_latest_run(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    lead_id: UUID,
) -> EnrichmentRun | None:
    """Return the most recent EnrichmentRun for the given lead, workspace-scoped."""
    result = await db.execute(
        select(EnrichmentRun)
        .join(Lead, EnrichmentRun.lead_id == Lead.id)
        .where(EnrichmentRun.lead_id == lead_id, Lead.workspace_id == workspace_id)
        .order_by(desc(EnrichmentRun.started_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def list_runs(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    lead_id: UUID,
    limit: int = 20,
) -> list[EnrichmentRun]:
    """Return recent EnrichmentRuns for the given lead, workspace-scoped."""
    result = await db.execute(
        select(EnrichmentRun)
        .join(Lead, EnrichmentRun.lead_id == Lead.id)
        .where(EnrichmentRun.lead_id == lead_id, Lead.workspace_id == workspace_id)
        .order_by(desc(EnrichmentRun.started_at))
        .limit(limit)
    )
    return list(result.scalars().all())
