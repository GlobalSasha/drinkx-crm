"""Celery app — broker + backend = Redis. One worker, one beat.

Tasks live in app.scheduled.jobs and are imported as a side effect when
this module loads (so beat schedule registration finds them).
"""
from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from app.config import get_settings

# Side-effect imports: hydrate the SQLAlchemy mapper registry with every
# domain model BEFORE any Celery task touches the DB. The worker process
# doesn't go through app.main, so without these the string-based forward
# references in Lead → Contact / Activity / Followup fail to resolve at
# task time with 'expression Contact failed to locate a name'.
from app.auth import models as _auth_models  # noqa: F401, E402
from app.pipelines import models as _pipeline_models  # noqa: F401, E402
from app.leads import models as _leads_models  # noqa: F401, E402
from app.contacts import models as _contacts_models  # noqa: F401, E402
from app.activity import models as _activity_models  # noqa: F401, E402
from app.followups import models as _followups_models  # noqa: F401, E402
from app.enrichment import models as _enrichment_models  # noqa: F401, E402
from app.daily_plan import models as _daily_plan_models  # noqa: F401, E402
from app.notifications import models as _notifications_models  # noqa: F401, E402
from app.audit import models as _audit_models  # noqa: F401, E402
from app.inbox import models as _inbox_models  # noqa: F401, E402

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
    "daily-email-digest": {
        "task": "app.scheduled.jobs.daily_email_digest",
        "schedule": crontab(minute=30),    # every hour at :30 UTC; runner filters by local hour=8
    },
    "gmail-incremental-sync": {
        "task": "app.scheduled.jobs.gmail_incremental_sync",
        "schedule": crontab(minute=f"*/{_s.gmail_sync_interval_minutes}"),
    },
}
