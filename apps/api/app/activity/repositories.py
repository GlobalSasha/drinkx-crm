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
#
# `activities.payload_json` is declared `JSON` in the model and lives on
# Postgres as `json` (not `jsonb`). Use `json_extract_path_text` —
# `jsonb_extract_path_text(json, ...)` doesn't exist and fails plan-time
# on this endpoint (production 500 on /feed reported 2026-05-16).
_SORT_KEY = func.coalesce(
    cast(
        func.json_extract_path_text(Activity.payload_json, "received_at"),
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


async def list_feed_for_lead(
    db: AsyncSession,
    lead_id: uuid.UUID,
    *,
    cursor: str | None = None,
    limit: int = 50,
) -> tuple[list[tuple[Activity, str | None]], str | None]:
    """Same ordering / cursor semantics as `list_for_lead`, but each
    row comes back as `(Activity, author_name)` — User.name resolved
    via LEFT JOIN so the frontend doesn't need an N+1 to label
    «Менеджер Иван» on every card.

    AI rows (`type='ai_suggestion'`) are rendered as Чак on the
    frontend regardless of the joined user — the join is still
    performed because some chat rows stamp the manager who asked the
    question, and we want that user's name for the *question* row in
    the same listing.
    """
    from app.auth.models import User  # local import to avoid model cycle

    q = (
        select(Activity, User.name)
        .select_from(Activity)
        .outerjoin(User, User.id == Activity.user_id)
        .where(Activity.lead_id == lead_id)
    )
    if cursor is not None:
        cursor_ts, cursor_id = _decode_cursor(cursor)
        q = q.where(
            or_(
                _SORT_KEY < cursor_ts,
                and_(_SORT_KEY == cursor_ts, Activity.id < cursor_id),
            )
        )
    q = q.order_by(_SORT_KEY.desc(), Activity.id.desc()).limit(limit + 1)

    rows = list((await db.execute(q)).all())

    if len(rows) > limit:
        rows = rows[:limit]
        last_act = rows[-1][0]
        next_cursor = _encode_cursor(_sort_key_of(last_act), last_act.id)
    else:
        next_cursor = None

    # Materialise as (Activity, name) tuples so callers can index.
    out = [(row[0], row[1]) for row in rows]
    return out, next_cursor
