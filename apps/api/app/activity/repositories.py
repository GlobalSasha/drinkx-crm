"""Activity data-access layer — SQLAlchemy 2.0 async."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.activity.models import Activity


def _encode_cursor(created_at: datetime, activity_id: uuid.UUID) -> str:
    """Composite cursor: 'ISO_TS|UUID' — stable when timestamps collide."""
    return f"{created_at.isoformat()}|{activity_id}"


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    ts_str, id_str = cursor.split("|", 1)
    return datetime.fromisoformat(ts_str), uuid.UUID(id_str)


async def list_for_lead(
    db: AsyncSession,
    lead_id: uuid.UUID,
    *,
    type_filter: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> tuple[list[Activity], str | None]:
    """Return (items, next_cursor).

    Cursor format: 'ISO_TIMESTAMP|UUID' (composite). The UUID component is the
    tiebreaker when two activities share the same `created_at` (millisecond-rounded
    timestamps from rapid inserts). Without it, page boundaries could silently
    skip rows. Sort + filter use lexicographic order on (created_at DESC, id DESC).
    """
    q = select(Activity).where(Activity.lead_id == lead_id)
    if type_filter is not None:
        q = q.where(Activity.type == type_filter)
    if cursor is not None:
        cursor_ts, cursor_id = _decode_cursor(cursor)
        # Composite "less than (created_at, id)" — order matches DESC sort below
        q = q.where(
            or_(
                Activity.created_at < cursor_ts,
                and_(Activity.created_at == cursor_ts, Activity.id < cursor_id),
            )
        )
    q = q.order_by(Activity.created_at.desc(), Activity.id.desc()).limit(limit + 1)

    result = await db.execute(q)
    rows = list(result.scalars().all())

    if len(rows) > limit:
        rows = rows[:limit]
        next_cursor = _encode_cursor(rows[-1].created_at, rows[-1].id)
    else:
        next_cursor = None

    return rows, next_cursor


async def get_by_id(
    db: AsyncSession, activity_id: uuid.UUID, lead_id: uuid.UUID
) -> Activity | None:
    result = await db.execute(
        select(Activity).where(Activity.id == activity_id, Activity.lead_id == lead_id)
    )
    return result.scalar_one_or_none()


async def create(
    db: AsyncSession,
    lead_id: uuid.UUID,
    user_id: uuid.UUID | None,
    payload_dict: dict[str, Any],
) -> Activity:
    activity = Activity(lead_id=lead_id, user_id=user_id, **payload_dict)
    db.add(activity)
    await db.flush()
    await db.refresh(activity)
    return activity


async def mark_task_done(
    db: AsyncSession, activity: Activity, completed_at: datetime
) -> Activity:
    activity.task_done = True
    activity.task_completed_at = completed_at
    await db.flush()
    await db.refresh(activity)
    return activity
