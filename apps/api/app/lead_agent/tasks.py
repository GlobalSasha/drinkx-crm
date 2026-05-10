"""Lead AI Agent — async cores for Celery tasks (Sprint 3.1 Phase C).

Per the project convention (`app/scheduled/jobs.py`), Celery `@task`
sync wrappers live in a single registry file alongside the rest of
the cron + manual jobs. The async cores live here so the domain code
stays self-contained — `jobs.py` only needs a 3-line wrapper.

The wrappers go through `_build_task_engine_and_factory` (per-task
NullPool engine — see Sprint 1.4 hotfix #4 for the «Future attached
to a different loop» bug this avoids).

Two cores:
  - `refresh_suggestion_async(lead_id)` — fired ad-hoc (REST
    `/refresh`, automation hooks in Phase E). Loads the lead, calls
    the runner, persists the suggestion to
    `lead.agent_state['suggestion']`.
  - `scan_silence_async()` — beat task on `*/6h`. Finds active leads
    where `last_activity_at` is older than `SCAN_SILENCE_DAYS` and
    dispatches `lead_agent_refresh_suggestion` for each via Celery
    so the work runs in the worker pool, not the beat process.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.lead_agent.runner import get_suggestion

log = structlog.get_logger()

# `scan_silence_async` flags a lead when its `last_activity_at` is
# older than this. The rotting evaluator uses the same column, so
# matching the convention keeps the «which leads need a poke» story
# consistent across the system.
SCAN_SILENCE_DAYS = 3


async def _resolve_stage_name(session: AsyncSession, lead: Any) -> str | None:
    """Best-effort lookup of `stages.name` for the lead's stage_id.
    Returns None on miss so `build_lead_context` drops the line
    instead of printing a UUID."""
    from app.pipelines.models import Stage

    stage_id = getattr(lead, "stage_id", None)
    if stage_id is None:
        return None
    try:
        res = await session.execute(select(Stage).where(Stage.id == stage_id))
        stage = res.scalar_one_or_none()
        return getattr(stage, "name", None) if stage is not None else None
    except Exception as exc:  # pragma: no cover — defensive
        log.warning("lead_agent.stage_lookup_failed", error=str(exc)[:200])
        return None


async def refresh_suggestion_async(lead_id: UUID) -> dict:
    """Async core for the `lead_agent_refresh_suggestion` Celery task.

    Pulls the lead, resolves stage name, fires the runner, and writes
    the result into `lead.agent_state['suggestion']`. Returns a
    summary dict consumed by the cron audit row.

    Failure modes:
      - lead missing → return early with {"status": "lead_not_found"}
      - runner returns None (LLM down / parse failure) → leaves the
        existing `agent_state['suggestion']` untouched and returns
        {"status": "no_suggestion"}; the previous banner stays on
        screen instead of going blank.
      - DB exception → re-raised so Celery retry / Sentry pick it up.
    """
    from app.scheduled.jobs import _build_task_engine_and_factory

    engine, factory = _build_task_engine_and_factory()
    try:
        async with factory() as session:
            res = await session.execute(
                select_lead_for_agent(lead_id)
            )
            lead = res.scalar_one_or_none()
            if lead is None:
                log.info("lead_agent.refresh.lead_not_found", lead_id=str(lead_id))
                return {"job": "lead_agent_refresh_suggestion", "status": "lead_not_found"}

            stage_name = await _resolve_stage_name(session, lead)
            suggestion = await get_suggestion(lead, stage_name=stage_name)

            if suggestion is None:
                log.info(
                    "lead_agent.refresh.no_suggestion",
                    lead_id=str(lead_id),
                )
                return {
                    "job": "lead_agent_refresh_suggestion",
                    "status": "no_suggestion",
                    "lead_id": str(lead_id),
                }

            current = dict(lead.agent_state or {})
            current["suggestion"] = suggestion.model_dump()
            lead.agent_state = current
            await session.commit()

            log.info(
                "lead_agent.refresh.ok",
                lead_id=str(lead_id),
                action_label=suggestion.action_label,
                confidence=suggestion.confidence,
            )
            return {
                "job": "lead_agent_refresh_suggestion",
                "status": "ok",
                "lead_id": str(lead_id),
                "action_label": suggestion.action_label,
                "confidence": suggestion.confidence,
            }
    finally:
        await engine.dispose()


def select_lead_for_agent(lead_id: UUID):
    """Tiny helper — keeps the import of `Lead` lazy so the Celery
    worker can run this task without dragging the full leads package
    at module import time (mirrors the lazy-import discipline used
    elsewhere in `app/scheduled/jobs.py`)."""
    from app.leads.models import Lead

    return select(Lead).where(Lead.id == lead_id)


async def scan_silence_async() -> dict:
    """Async core for the `lead_agent_scan_silence` Celery beat task.

    Finds active leads (`assignment_status='assigned'`) whose
    `last_activity_at` is older than `SCAN_SILENCE_DAYS` and queues
    one `lead_agent_refresh_suggestion(lead_id)` per match. Returns
    a summary dict for the cron audit row.

    Dispatch goes through `Celery.delay` so the actual LLM work runs
    in the worker pool — beat keeps a tight loop and does not block
    on per-lead async cores.
    """
    from app.leads.models import Lead
    from app.scheduled.jobs import _build_task_engine_and_factory

    threshold = datetime.now(timezone.utc) - timedelta(days=SCAN_SILENCE_DAYS)
    engine, factory = _build_task_engine_and_factory()
    try:
        async with factory() as session:
            res = await session.execute(
                select(Lead.id).where(
                    Lead.assignment_status == "assigned",
                    Lead.last_activity_at.is_not(None),
                    Lead.last_activity_at < threshold,
                )
            )
            ids = [row[0] for row in res.fetchall()]

        # Lazy import — avoids a circular `jobs → tasks → jobs` chain
        # when the worker imports the registry on startup.
        from app.scheduled.jobs import lead_agent_refresh_suggestion

        for lid in ids:
            lead_agent_refresh_suggestion.delay(str(lid))

        log.info("lead_agent.scan_silence.dispatched", candidates=len(ids))
        return {
            "job": "lead_agent_scan_silence",
            "candidates": len(ids),
        }
    finally:
        await engine.dispose()
