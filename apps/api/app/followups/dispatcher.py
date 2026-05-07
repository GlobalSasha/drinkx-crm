"""Cron-driven follow-up reminder emitter.

Iterates Followups due within the next 24h that haven't been dispatched
yet. For each: creates an Activity(type='reminder', reminder_trigger_at=
followup.due_at) attached to the same lead, and stamps
followup.dispatched_at = now.

Idempotent: re-running within the same window is a no-op because
dispatched_at is non-null.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.activity.models import Activity, ActivityType
from app.followups.models import Followup

log = structlog.get_logger()

_LOOKAHEAD = timedelta(hours=24)


async def run_followup_dispatch(session: AsyncSession) -> int:
    """Returns the number of activity rows created this tick."""
    now = datetime.now(timezone.utc)
    res = await session.execute(
        select(Followup).where(
            Followup.dispatched_at.is_(None),
            Followup.due_at.is_not(None),
            Followup.due_at <= now + _LOOKAHEAD,
            Followup.status.in_(("pending", "active")),
        )
    )
    followups = list(res.scalars().all())

    created = 0
    for fu in followups:
        activity = Activity(
            lead_id=fu.lead_id,
            user_id=None,           # system-generated
            type=ActivityType.reminder.value,
            reminder_trigger_at=fu.due_at,
            payload_json={"followup_id": str(fu.id), "name": fu.name},
            body=fu.name,
        )
        session.add(activity)
        fu.dispatched_at = now
        created += 1

    await session.commit()
    return created
