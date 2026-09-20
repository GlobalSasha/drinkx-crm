"""Celery app — broker + backend = Redis. One worker, one beat.

Tasks live in app.scheduled.jobs and are imported as a side effect when
this module loads (so beat schedule registration finds them).
"""
from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.config import get_settings

# Реестр моделей: наполняет mapper-реестр SQLAlchemy всеми доменными
# моделями ДО того, как задача Celery тронет БД. Worker не проходит через
# app.main, и без этого строковые forward-ссылки Lead → Contact / Activity /
# Followup падают во время задачи с 'expression Contact failed to locate a
# name'. Раньше здесь лежал ручной список из 17 доменов (из 27) — он тихо
# отставал от кода; app.models_registry — единственный список, за полнотой
# которого следит tests/test_models_registry_completeness.py. Импортирует
# только models.py, сеть и БД не трогает.
import app.models_registry  # noqa: F401, E402

_s = get_settings()

# Same JSON-to-file logging as the API, so worker/beat logs land in the
# shared /app/logs/app.log that GET /admin/logs reads.
from app.observability import configure_logging  # noqa: E402

configure_logging(_s)

celery_app = Celery(
    "drinkx",
    broker=_s.redis_url,
    backend=_s.redis_url,
    include=["app.scheduled.jobs"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",            # internal scheduling clock; per-user timezone handled inside the task
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,       # hard kill at 10 min
    task_soft_time_limit=540,
    worker_max_tasks_per_child=200,    # cycle workers to release memory
    broker_connection_retry_on_startup=True,
)

celery_app.conf.beat_schedule = {
    "daily-plan-generator": {
        "task": "app.scheduled.jobs.daily_plan_generator",
        "schedule": crontab(minute=0),    # every hour at :00 UTC
    },
    "followup-reminder-dispatcher": {
        "task": "app.scheduled.jobs.followup_reminder_dispatcher",
        "schedule": crontab(minute="*/15"),
    },
    "daily-email-digest": {
        "task": "app.scheduled.jobs.daily_email_digest",
        "schedule": crontab(minute=30),    # every hour at :30 UTC; runner filters by local hour=8
    },
    "gmail-incremental-sync": {
        "task": "app.scheduled.jobs.gmail_incremental_sync",
        "schedule": crontab(minute=f"*/{_s.gmail_sync_interval_minutes}"),
    },
    "automation-step-scheduler": {
        "task": "app.scheduled.jobs.automation_step_scheduler",
        "schedule": crontab(minute="*/5"),
    },
    "lead-agent-scan-silence": {
        # Sprint 3.1 Phase C — every 6 hours, refresh banners for
        # quiet leads. Per-lead work is dispatched into the worker
        # pool inside the task body, keeping the beat tick light.
        "task": "app.scheduled.jobs.lead_agent_scan_silence",
        "schedule": crontab(minute=0, hour="*/6"),
    },
    "pool-auto-enrich": {
        # Sprint 3.9 G5 — daily at 03:00 UTC (06:00 MSK). Selects pool
        # leads with no succeeded run in 30 days and enqueues lightweight
        # enrichment for each, staggered 3 s apart.
        "task": "app.scheduled.jobs.pool_auto_enrich_batch",
        "schedule": crontab(hour=3, minute=0),
    },
    "expire-stuck-enrichment-runs": {
        # S-2 — порог гашения 5 минут (STUCK_RUN_TIMEOUT_SECONDS), так что
        # и проход раз в 5 минут.
        "task": "app.scheduled.jobs.expire_stuck_enrichment_runs",
        "schedule": crontab(minute="*/5"),
    },
    "purge-orphan-storage-files": {
        "task": "app.scheduled.jobs.purge_orphan_storage_files",
        "schedule": crontab(hour=3, minute=30, day_of_week=0),  # Sundays 03:30 UTC
    },
}
