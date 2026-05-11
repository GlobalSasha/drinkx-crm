"""Team stats services — Sprint 3.4 G1.

Period resolution + fan-out to the four per-user repository calls,
zipped into the response shape.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.team import repositories as repo
from app.users import repositories as users_repo


VALID_PERIODS = ("today", "week", "month")


def resolve_period(period: str) -> tuple[datetime, datetime]:
    """Return (from_, to) UTC datetimes for the period label.

    `today` = the current UTC day from 00:00 to 23:59:59.
    `week`  = the trailing 7 days inclusive of today (today − 6 → today).
    `month` = the trailing 30 days inclusive of today.
    """
    if period not in VALID_PERIODS:
        raise ValueError(f"invalid period: {period}")
    now = datetime.now(timezone.utc)
    end_of_today = now.replace(hour=23, minute=59, second=59, microsecond=0)
    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "today":
        return start_of_today, end_of_today
    if period == "week":
        return start_of_today - timedelta(days=6), end_of_today
    return start_of_today - timedelta(days=29), end_of_today


class UserNotFound(Exception):
    """404 from router."""


async def team_stats(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    period: str,
) -> dict:
    from_, to = resolve_period(period)
    users, _total = await users_repo.list_for_workspace(
        db, workspace_id=workspace_id
    )
    user_ids = [u.id for u in users]

    kp = await repo.kp_sent_per_user(
        db, workspace_id=workspace_id, user_ids=user_ids, from_=from_, to=to
    )
    taken = await repo.leads_taken_per_user(
        db, workspace_id=workspace_id, user_ids=user_ids, from_=from_, to=to
    )
    moved = await repo.leads_moved_per_user(
        db, workspace_id=workspace_id, user_ids=user_ids, from_=from_, to=to
    )
    tasks = await repo.tasks_completed_per_user(
        db, workspace_id=workspace_id, user_ids=user_ids, from_=from_, to=to
    )
    last_active = await repo.last_active_per_user(
        db, workspace_id=workspace_id, user_ids=user_ids
    )

    managers = []
    for u in users:
        last_act = last_active.get(u.id) or u.last_login_at
        managers.append({
            "user_id": u.id,
            "name": u.name or u.email,
            "email": u.email,
            "avatar_url": None,
            "role": u.role,
            "stats": {
                "kp_sent": kp.get(u.id, 0),
                "leads_taken_from_pool": taken.get(u.id, 0),
                "leads_moved": moved.get(u.id, 0),
                "tasks_completed": tasks.get(u.id, 0),
            },
            "last_active_at": last_act,
        })

    return {
        "period": period,
        "from_": from_,
        "to": to,
        "managers": managers,
    }


async def manager_stats(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    period: str,
) -> dict:
    from_, to = resolve_period(period)
    user = await users_repo.get_by_id(
        db, user_id=user_id, workspace_id=workspace_id
    )
    if user is None:
        raise UserNotFound(str(user_id))

    kp = await repo.kp_sent_per_user(
        db, workspace_id=workspace_id, user_ids=[user.id],
        from_=from_, to=to,
    )
    taken = await repo.leads_taken_per_user(
        db, workspace_id=workspace_id, user_ids=[user.id],
        from_=from_, to=to,
    )
    moved = await repo.leads_moved_per_user(
        db, workspace_id=workspace_id, user_ids=[user.id],
        from_=from_, to=to,
    )
    tasks = await repo.tasks_completed_per_user(
        db, workspace_id=workspace_id, user_ids=[user.id],
        from_=from_, to=to,
    )
    daily = await repo.daily_breakdown(
        db, workspace_id=workspace_id, user_id=user.id,
        from_=from_, to=to,
    )

    return {
        "user_id": user.id,
        "name": user.name or user.email,
        "email": user.email,
        "role": user.role,
        "period": period,
        "from_": from_,
        "to": to,
        "stats": {
            "kp_sent": kp.get(user.id, 0),
            "leads_taken_from_pool": taken.get(user.id, 0),
            "leads_moved": moved.get(user.id, 0),
            "tasks_completed": tasks.get(user.id, 0),
        },
        "daily": daily,
    }
