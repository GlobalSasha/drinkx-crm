"""Celery app — broker + backend = Redis. One worker, one beat.

Tasks live in app.scheduled.jobs and are imported as a side effect when
this module loads (so beat schedule registration finds them).
"""
from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.config import get_settings

_s = get_settings()

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
}
