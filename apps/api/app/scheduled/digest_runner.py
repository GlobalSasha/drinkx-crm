"""Daily digest cron runner.

Iterates active users and fires the digest builder for users whose local
clock just hit 08:00 (matched by hour, since beat fires us at minute=30
of every hour — i.e. 08:30 local).

Per-user failure must NOT kill the tick — same defensive pattern as
daily_plan_runner.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.notifications.digest import build_digest_for_user

log = structlog.get_logger()

_TARGET_LOCAL_HOUR = 8
_INACTIVITY_DAYS = 30


def _local_hour_now(tz_name: str | None) -> int | None:
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(tz_name) if tz_name else timezone.utc
    except Exception:
        return None
    return datetime.now(tz).hour


async def run_daily_digest_for_all_users(session: AsyncSession) -> int:
    """Returns the count of digests that were sent (or stubbed)."""
    threshold = datetime.now(timezone.utc) - timedelta(days=_INACTIVITY_DAYS)
    res = await session.execute(
        select(User).where(User.last_login_at >= threshold)
    )
    users = list(res.scalars().all())

    sent_count = 0
    for u in users:
        local_hour = _local_hour_now(u.timezone)
        if local_hour != _TARGET_LOCAL_HOUR:
            continue  # not their 08:30 yet
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(u.timezone) if u.timezone else timezone.utc
            local_today: date = datetime.now(tz).date()
        except Exception:
            local_today = datetime.now(timezone.utc).date()

        try:
            sent = await build_digest_for_user(
                session,
                user_id=u.id,
                workspace_id=u.workspace_id,
                user_name=u.name or u.email,
                user_email=u.email,
                today=local_today,
            )
            if sent:
                sent_count += 1
        except Exception as exc:
            log.warning(
                "digest_runner.user_failed",
                user_id=str(u.id),
                error=str(exc)[:300],
            )
    return sent_count
