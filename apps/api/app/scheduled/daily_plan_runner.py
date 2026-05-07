"""Iterate active managers, fire generate_for_user() only for users
whose local clock is 08:00 right now."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.daily_plan.services import generate_for_user

log = structlog.get_logger()

_TARGET_LOCAL_HOUR = 8

# How long a user can be away before we stop generating their plan
_INACTIVITY_DAYS = 30


def _local_hour_now(tz_name: str | None) -> int | None:
    """Return current local hour-of-day for the given IANA tz (e.g. 'Europe/Moscow'),
    or None if the tz string is unrecognized."""
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(tz_name) if tz_name else timezone.utc
    except Exception:
        return None
    now = datetime.now(tz)
    return now.hour


async def run_daily_plan_for_all_users(session: AsyncSession) -> int:
    """Returns the number of plans generated this tick."""
    # Active managers: have logged in in the last 30 days; any role.
    threshold = datetime.now(timezone.utc) - timedelta(days=_INACTIVITY_DAYS)
    res = await session.execute(
        select(User).where(User.last_login_at >= threshold)
    )
    users = list(res.scalars().all())

    generated = 0
    for u in users:
        local_hour = _local_hour_now(u.timezone)
        if local_hour != _TARGET_LOCAL_HOUR:
            continue  # not their morning yet
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(u.timezone) if u.timezone else timezone.utc
            local_today: date = datetime.now(tz).date()
        except Exception:
            local_today = datetime.now(timezone.utc).date()

        try:
            await generate_for_user(session, user=u, plan_date=local_today)
            generated += 1
        except Exception as e:
            log.warning("daily_plan_runner.user_failed", user_id=str(u.id), error=str(e))
    return generated
