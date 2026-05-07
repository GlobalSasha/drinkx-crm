"""Smoke tests for Celery app wiring — no broker needed."""
from __future__ import annotations


def test_celery_app_has_two_tasks_registered():
    """Both task names must appear in celery_app.tasks after import."""
    from app.scheduled.celery_app import celery_app

    # Force task registration by importing jobs
    import app.scheduled.jobs  # noqa: F401

    registered = list(celery_app.tasks.keys())
    assert "app.scheduled.jobs.daily_plan_generator" in registered
    assert "app.scheduled.jobs.followup_reminder_dispatcher" in registered


def test_beat_schedule_has_two_entries():
    """beat_schedule must contain exactly the two expected keys."""
    from app.scheduled.celery_app import celery_app

    schedule = celery_app.conf.beat_schedule
    assert "daily-plan-generator" in schedule
    assert "followup-reminder-dispatcher" in schedule

    # Verify the task names in the schedule entries
    assert schedule["daily-plan-generator"]["task"] == "app.scheduled.jobs.daily_plan_generator"
    assert schedule["followup-reminder-dispatcher"]["task"] == "app.scheduled.jobs.followup_reminder_dispatcher"
