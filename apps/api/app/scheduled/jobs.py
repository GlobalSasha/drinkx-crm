"""Cron tasks. Each task wraps an async core in a fresh DB session.

Pattern:
- @celery_app.task signature is sync (Celery requirement)
- It opens a DB session via get_session_factory()
- It calls an async core function with that session
- A ScheduledJob audit row is written on every invocation with affected_count + error
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import structlog

from app.db import get_session_factory
from app.scheduled.celery_app import celery_app

log = structlog.get_logger()


@celery_app.task(name="app.scheduled.jobs.daily_plan_generator")
def daily_plan_generator() -> dict:
    """Hourly: process workspaces where the local clock just hit 08:00."""
    from app.scheduled.daily_plan_runner import run_daily_plan_for_all_users
    return asyncio.run(_run("daily_plan_generator", run_daily_plan_for_all_users))


@celery_app.task(name="app.scheduled.jobs.followup_reminder_dispatcher")
def followup_reminder_dispatcher() -> dict:
    """Every 15 min: create Activity reminders for followups due within 24h."""
    from app.followups.dispatcher import run_followup_dispatch
    return asyncio.run(_run("followup_reminder_dispatcher", run_followup_dispatch))


async def _run(job_name: str, async_core) -> dict:
    """Common audit + execution wrapper."""
    from app.daily_plan.models import ScheduledJob

    factory = get_session_factory()
    started = datetime.now(timezone.utc)
    affected = 0
    error: str | None = None

    async with factory() as session:
        audit = ScheduledJob(
            id=uuid4(),
            job_name=job_name,
            started_at=started,
            status="running",
        )
        session.add(audit)
        await session.commit()

        try:
            affected = await async_core(session)
            audit.status = "succeeded"
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            audit.status = "failed"
            audit.error = error[:2000]
            log.exception("scheduled.failed", job=job_name)
        finally:
            audit.affected_count = affected
            audit.finished_at = datetime.now(timezone.utc)
            await session.commit()

    return {"job": job_name, "affected": affected, "error": error}
