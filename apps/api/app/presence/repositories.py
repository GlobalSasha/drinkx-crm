"""Presence repositories — active-minute tracking. Workspace-scoped."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def record_ping(
    db: AsyncSession, *, user_id: uuid.UUID, workspace_id: uuid.UUID
) -> None:
    """Insert the current wall-clock minute for this user. Idempotent per minute."""
    sql = text("""
        INSERT INTO presence_minutes (user_id, workspace_id, minute)
        VALUES (:uid, :wid, date_trunc('minute', now()))
        ON CONFLICT (user_id, minute) DO NOTHING
    """)
    await db.execute(sql, {"uid": user_id, "wid": workspace_id})


async def active_minutes_range(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_ids: list[uuid.UUID],
    from_: datetime,
    to: datetime,
) -> dict[uuid.UUID, int]:
    if not user_ids:
        return {}
    sql = text("""
        SELECT user_id, count(*) AS n
        FROM presence_minutes
        WHERE workspace_id = :wid
          AND user_id = ANY(:uids)
          AND minute >= :from_ AND minute <= :to
        GROUP BY user_id
    """)
    rows = (
        await db.execute(
            sql, {"wid": workspace_id, "uids": user_ids, "from_": from_, "to": to}
        )
    ).all()
    return {r.user_id: int(r.n) for r in rows}


async def active_daily(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    from_: datetime,
    to: datetime,
) -> list[dict]:
    """Per-day minute counts for one user, ascending by date."""
    sql = text("""
        SELECT minute::date AS day, count(*) AS n
        FROM presence_minutes
        WHERE workspace_id = :wid
          AND user_id = :uid
          AND minute >= :from_ AND minute <= :to
        GROUP BY minute::date
        ORDER BY day ASC
    """)
    rows = (
        await db.execute(
            sql, {"wid": workspace_id, "uid": user_id, "from_": from_, "to": to}
        )
    ).all()
    return [{"date": r.day, "minutes": int(r.n)} for r in rows]
