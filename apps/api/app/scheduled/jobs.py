"""Cron tasks. Each task wraps an async core in a fresh DB session.

Pattern:
- @celery_app.task signature is sync (Celery requirement)
- It opens a DB session via get_session_factory()
- It calls an async core function with that session
- A ScheduledJob audit row is written on every invocation with affected_count + error
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from uuid import UUID, uuid4

import structlog

from app.db import get_session_factory  # noqa: F401  # kept for tests that monkeypatch this symbol
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


@celery_app.task(name="app.scheduled.jobs.daily_email_digest")
def daily_email_digest() -> dict:
    """Hourly at :30 — emails the digest to users whose local clock is 08."""
    from app.scheduled.digest_runner import run_daily_digest_for_all_users
    return asyncio.run(_run("daily_email_digest", run_daily_digest_for_all_users))


@celery_app.task(name="app.scheduled.jobs.regenerate_for_user")
def regenerate_for_user(user_id: str, plan_date_iso: str) -> dict:
    """Manual trigger from the UI. Generates one user's plan, ignoring the
    08:00-local-time gate the hourly cron uses."""
    return asyncio.run(_run_one_user_regen(UUID(user_id), date.fromisoformat(plan_date_iso)))


@celery_app.task(name="app.scheduled.jobs.gmail_history_sync")
def gmail_history_sync(user_id: str) -> dict:
    """One-time backfill dispatched from /api/inbox/gmail/callback.

    Pulls the last GMAIL_HISTORY_MONTHS of mail for the given user and
    seeds the incremental cursor.
    """
    return asyncio.run(_run_gmail_history_sync(UUID(user_id)))


@celery_app.task(name="app.scheduled.jobs.gmail_incremental_sync")
def gmail_incremental_sync() -> dict:
    """Every 5 min: process new messages for every active gmail channel."""
    from app.inbox.sync import incremental_sync_for_all
    return asyncio.run(_run("gmail_incremental_sync", incremental_sync_for_all))


def _build_task_engine_and_factory():
    """Each Celery task needs its own engine because asyncio.run() creates a
    fresh event loop per invocation, while asyncpg connections are bound to
    the loop they were created on. Re-using a global engine across loops
    raises 'Future attached to a different loop'. NullPool is right for
    short-lived cron work — connections are created and closed per task.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.config import get_settings

    s = get_settings()
    engine = create_async_engine(
        s.database_url,
        echo=False,
        poolclass=NullPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, factory


async def _run_gmail_history_sync(user_id: UUID) -> dict:
    """Per-task NullPool engine + audit row for the one-shot backfill."""
    from app.daily_plan.models import ScheduledJob
    from app.inbox.sync import history_sync_for_user

    engine, factory = _build_task_engine_and_factory()
    started = datetime.now(timezone.utc)
    affected = 0
    error: str | None = None
    try:
        async with factory() as session:
            audit = ScheduledJob(
                id=uuid4(),
                job_name="gmail_history_sync",
                started_at=started,
                status="running",
            )
            session.add(audit)
            await session.commit()

            try:
                affected = await history_sync_for_user(session, user_id=user_id)
                audit.status = "succeeded"
            except Exception as e:
                error = f"{type(e).__name__}: {e}"
                audit.status = "failed"
                audit.error = error[:2000]
                log.exception("gmail_history_sync.failed", user_id=str(user_id))
            finally:
                audit.affected_count = affected
                audit.finished_at = datetime.now(timezone.utc)
                await session.commit()
    finally:
        await engine.dispose()

    return {
        "job": "gmail_history_sync",
        "user_id": str(user_id),
        "affected": affected,
        "error": error,
    }


async def _run_one_user_regen(user_id: UUID, plan_date: date) -> dict:
    engine, factory = _build_task_engine_and_factory()
    try:
        async with factory() as session:
            from sqlalchemy import select

            from app.auth.models import User
            from app.daily_plan.services import generate_for_user

            res = await session.execute(select(User).where(User.id == user_id))
            user = res.scalar_one_or_none()
            if user is None:
                return {"job": "regenerate_for_user", "error": "user_not_found"}
            try:
                plan = await generate_for_user(session, user=user, plan_date=plan_date)
                return {"job": "regenerate_for_user", "plan_id": str(plan.id), "status": plan.status}
            except Exception as e:
                log.exception("regenerate_for_user.failed", user_id=str(user_id))
                return {"job": "regenerate_for_user", "error": f"{type(e).__name__}: {e}"}
    finally:
        await engine.dispose()


async def _run(job_name: str, async_core) -> dict:
    """Common audit + execution wrapper. Builds a fresh engine+session
    factory per task — see _build_task_engine_and_factory for why."""
    from app.daily_plan.models import ScheduledJob

    engine, factory = _build_task_engine_and_factory()
    started = datetime.now(timezone.utc)
    affected = 0
    error: str | None = None

    try:
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
    finally:
        await engine.dispose()

    return {"job": job_name, "affected": affected, "error": error}
