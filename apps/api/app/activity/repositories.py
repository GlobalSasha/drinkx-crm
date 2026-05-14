"""Activity data-access layer — SQLAlchemy 2.0 async."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, and_, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.activity.models import Activity


# Sort key: prefer payload_json.received_at (set by the Gmail ingest path
# in app/inbox/processor.py — ISO 8601 string) so a multi-month backfill
# orders by send time, not by ingest time. Falls back to created_at for
# rows without a payload received_at (notes, tasks, etc.).
_SORT_KEY = func.coalesce(
    cast(
        func.jsonb_extract_path_text(Activity.payload_json, "received_at"),
        DateTime(timezone=True),
    ),
    Activity.created_at,
)


def _sort_key_of(row: Activity) -> datetime:
    raw = (row.payload_json or {}).get("received_at")
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            pass
    return row.created_at


def _encode_cursor(sort_key: datetime, activity_id: uuid.UUID) -> str:
    """Composite cursor: 'ISO_TS|UUID' — stable when timestamps collide.

    `sort_key` is the COALESCE(received_at, created_at) value, matching the
    ORDER BY expression. Encoding the actual sort key (not raw created_at)
    keeps pagination consistent when the two diverge.
    """
    return f"{sort_key.isoformat()}|{activity_id}"


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

    Cursor format: 'ISO_TIMESTAMP|UUID' (composite). The timestamp is the
    sort key — COALESCE(payload_json.received_at, created_at). The UUID
    component is the tiebreaker when two activities share the same sort
    key (millisecond-rounded timestamps from rapid inserts). Without it,
    page boundaries could silently skip rows. Sort + filter use
    lexicographic order on (sort_key DESC, id DESC).
    """
    q = select(Activity).where(Activity.lead_id == lead_id)
    if type_filter is not None:
        q = q.where(Activity.type == type_filter)
    if cursor is not None:
        cursor_ts, cursor_id = _decode_cursor(cursor)
        # Composite "less than (sort_key, id)" — order matches DESC sort below
        q = q.where(
            or_(
                _SORT_KEY < cursor_ts,
                and_(_SORT_KEY == cursor_ts, Activity.id < cursor_id),
            )
        )
    q = q.order_by(_SORT_KEY.desc(), Activity.id.desc()).limit(limit + 1)

    result = await db.execute(q)
    rows = list(result.scalars().all())

    if len(rows) > limit:
        rows = rows[:limit]
        next_cursor = _encode_cursor(_sort_key_of(rows[-1]), rows[-1].id)
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
