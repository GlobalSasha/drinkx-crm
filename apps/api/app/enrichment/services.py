"""Enrichment service layer — workspace-scoped EnrichmentRun management."""
from __future__ import annotations

import uuid as _uuid_mod
from datetime import datetime, timedelta, timezone
from uuid import UUID

import structlog
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enrichment.budget import has_budget_remaining, _daily_cap_usd, get_daily_spend_usd
from app.enrichment.concurrency import is_at_concurrency_limit
from app.enrichment.models import EnrichmentRun
from app.leads.models import Lead
from app.leads.services import LeadNotFound

log = structlog.get_logger()

# Stuck-run guard: a BG task that crashed mid-run leaves the row at status
# 'running' forever. The UI polls /latest and spins indefinitely. After this
# many seconds we declare the run failed so the UI can stop spinning.
STUCK_RUN_TIMEOUT_SECONDS = 300  # 5 minutes


class EnrichmentAlreadyRunning(Exception):
    def __init__(self, run_id: UUID):
        super().__init__(f"enrichment already running: {run_id}")
        self.run_id = run_id


class EnrichmentConcurrencyLimit(Exception):
    """Already at AI_MAX_PARALLEL_JOBS running runs for the workspace."""


class EnrichmentBudgetExceeded(Exception):
    def __init__(self, spent: float, cap: float):
        super().__init__(f"daily AI budget exceeded: ${spent:.2f} / ${cap:.2f}")
        self.spent = spent
        self.cap = cap


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
    Raises EnrichmentConcurrencyLimit if workspace is at AI_MAX_PARALLEL_JOBS running runs.
    Raises EnrichmentBudgetExceeded if workspace has exceeded daily AI budget.
    """
    # Verify lead exists in this workspace
    result = await db.execute(
        select(Lead).where(Lead.id == lead_id, Lead.workspace_id == workspace_id)
    )
    lead = result.scalar_one_or_none()
    if lead is None:
        raise LeadNotFound(lead_id)

    # Guard: workspace concurrency limit
    if await is_at_concurrency_limit(db, workspace_id):
        raise EnrichmentConcurrencyLimit()

    # Guard: daily budget
    if not await has_budget_remaining(workspace_id):
        spent = await get_daily_spend_usd(workspace_id)
        cap = _daily_cap_usd()
        raise EnrichmentBudgetExceeded(spent, cap)

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

    # Audit: enrichment.trigger. user_id may be None for system cron triggers.
    from app.audit.audit import log as audit_log

    await audit_log(
        db,
        action="enrichment.trigger",
        workspace_id=workspace_id,
        user_id=user_id,
        entity_type="lead",
        entity_id=lead_id,
        delta={"run_id": str(run.id)},
    )
    return run


async def get_latest_run(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    lead_id: UUID,
) -> EnrichmentRun | None:
    """Return the most recent EnrichmentRun for the given lead, workspace-scoped.

    Auto-expires zombie 'running' rows: if a BG task crashed (worker restart,
    asyncio mishap, etc.) the row never transitions out of 'running' and the
    UI spinner runs forever. We flip rows older than STUCK_RUN_TIMEOUT_SECONDS
    to 'failed' so the spinner stops.
    """
    result = await db.execute(
        select(EnrichmentRun)
        .join(Lead, EnrichmentRun.lead_id == Lead.id)
        .where(EnrichmentRun.lead_id == lead_id, Lead.workspace_id == workspace_id)
        .order_by(desc(EnrichmentRun.started_at))
        .limit(1)
    )
    run = result.scalar_one_or_none()
    if run is None:
        return None

    if run.status == "running":
        started = run.started_at
        # started_at is timezone-aware (server_default=now()) — make naive
        # comparisons robust by coercing both sides to UTC-aware.
        if started is not None and started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        cutoff = datetime.now(tz=timezone.utc) - timedelta(seconds=STUCK_RUN_TIMEOUT_SECONDS)
        if started is not None and started < cutoff:
            run.status = "failed"
            run.error = (
                run.error
                or f"stuck-run guard: no completion within {STUCK_RUN_TIMEOUT_SECONDS}s"
            )
            run.finished_at = datetime.now(tz=timezone.utc)
            await db.commit()
            log.warning(
                "enrichment.stuck_run_expired",
                run_id=str(run.id),
                lead_id=str(lead_id),
                age_seconds=int((datetime.now(tz=timezone.utc) - started).total_seconds()),
            )
    return run


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
