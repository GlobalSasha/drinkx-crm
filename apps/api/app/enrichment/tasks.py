"""Sprint 3.9 G5 — pool_auto_enrich_batch async core.

Imported at module top so test's patch.object(t, "get_pool_leads_needing_enrichment")
resolves against this module's namespace.
"""
from __future__ import annotations

import structlog

from app.leads.repositories import get_pool_leads_needing_enrichment  # noqa: F401 — patched in tests
from app.scheduled.jobs import _build_task_engine_and_factory  # noqa: F401 — patched in tests

log = structlog.get_logger()


async def _running_run_exists(db, lead_id) -> bool:
    """Return True if there is already a 'running' EnrichmentRun for this lead."""
    from sqlalchemy import select

    from app.enrichment.models import EnrichmentRun

    res = await db.execute(
        select(EnrichmentRun.id)
        .where(EnrichmentRun.lead_id == lead_id, EnrichmentRun.status == "running")
        .limit(1)
    )
    return res.scalar_one_or_none() is not None


async def _enqueue_lightweight_enrich(db, lead, *, countdown: int) -> None:
    """Create an EnrichmentRun row + dispatch lightweight enrichment via Celery.

    Uses trigger_enrichment (system-initiated: user_id=None) to create the run
    row and honour concurrency / budget guards. Gracefully skips the lead if
    any guard raises.
    """
    from app.enrichment.services import (
        EnrichmentAlreadyRunning,
        EnrichmentBudgetExceeded,
        EnrichmentConcurrencyLimit,
        trigger_enrichment,
    )
    from app.scheduled.celery_app import celery_app

    try:
        run = await trigger_enrichment(
            db,
            workspace_id=lead.workspace_id,
            user_id=None,
            lead_id=lead.id,
        )
    except (EnrichmentAlreadyRunning, EnrichmentConcurrencyLimit, EnrichmentBudgetExceeded) as exc:
        log.info(
            "pool_auto_enrich.skipped_guard",
            lead_id=str(lead.id),
            reason=type(exc).__name__,
        )
        return

    await db.commit()
    celery_app.send_task(
        "app.scheduled.jobs.run_enrichment_task",
        args=[str(run.id), "lightweight"],
        countdown=countdown,
    )


async def _run_pool_auto_enrich_batch(limit: int = 20) -> dict:
    """Select stale pool leads and enqueue lightweight enrichment for each,
    staggered 3 s apart. Skips leads that already have a running run."""
    engine, factory = _build_task_engine_and_factory()
    scheduled = 0
    try:
        async with factory() as db:
            leads = await get_pool_leads_needing_enrichment(db, limit=limit)
            for i, lead in enumerate(leads):
                if await _running_run_exists(db, lead.id):
                    continue
                await _enqueue_lightweight_enrich(db, lead, countdown=i * 3)
                scheduled += 1
    finally:
        await engine.dispose()

    log.info("pool_auto_enrich.scheduled", count=scheduled)
    return {"job": "pool_auto_enrich_batch", "scheduled": scheduled}
