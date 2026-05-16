"""Activity service layer — business validation on top of repositories."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.activity import repositories as repo
from app.activity.models import Activity, ActivityType
from app.leads import repositories as leads_repo
from app.leads.services import LeadNotFound

_VALID_TYPES = {t.value for t in ActivityType}


class ActivityNotFound(Exception):
    pass


class ActivityWrongType(Exception):
    pass


def _validate_type(type_: str) -> None:
    if type_ not in _VALID_TYPES:
        raise ValueError(f"Invalid activity type '{type_}'. Allowed: {_VALID_TYPES}")


async def _get_lead_or_raise(
    db: AsyncSession, lead_id: uuid.UUID, workspace_id: uuid.UUID
) -> None:
    lead = await leads_repo.get_by_id(db, lead_id, workspace_id)
    if lead is None:
        raise LeadNotFound(lead_id)


async def list_activities(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
    *,
    type_filter: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> tuple[list[Activity], str | None]:
    await _get_lead_or_raise(db, lead_id, workspace_id)
    return await repo.list_for_lead(
        db, lead_id, type_filter=type_filter, cursor=cursor, limit=limit
    )


async def create_activity(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
    user_id: uuid.UUID,
    payload_dict: dict,
) -> Activity:
    await _get_lead_or_raise(db, lead_id, workspace_id)
    _validate_type(payload_dict.get("type", ""))
    if payload_dict.get("type") == ActivityType.task.value and not payload_dict.get("task_due_at"):
        raise ValueError("task_due_at is required for task activities")
    return await repo.create(db, lead_id, user_id, payload_dict)


async def complete_task(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
    activity_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Activity:
    await _get_lead_or_raise(db, lead_id, workspace_id)
    activity = await repo.get_by_id(db, activity_id, lead_id)
    if activity is None:
        raise ActivityNotFound(activity_id)
    if activity.type != ActivityType.task.value:
        raise ActivityWrongType("Cannot complete non-task activity")
    if activity.task_done:
        return activity  # idempotent
    return await repo.mark_task_done(db, activity, datetime.now(timezone.utc))


# Author-name resolution for the unified feed. Anything written by the
# AI runner / chat handler is presented as «Чак» regardless of the
# user_id stamped on the row (some chat answers carry the asking
# manager's id for audit; the visible author is still the AI).
_AI_AUTHOR_NAME = "Чак"
_AI_TYPES = {ActivityType.ai_suggestion.value}


def _resolve_author_name(activity: Activity, joined_name: str | None) -> str | None:
    if activity.type in _AI_TYPES:
        return _AI_AUTHOR_NAME
    return joined_name


async def list_feed(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
    *,
    cursor: str | None = None,
    limit: int = 50,
) -> tuple[list[tuple[Activity, str | None]], str | None]:
    """Lists feed items (no type filter — the unified feed shows
    everything) and resolves `author_name` per row via the AI override
    rule defined above."""
    await _get_lead_or_raise(db, lead_id, workspace_id)
    rows, next_cursor = await repo.list_feed_for_lead(
        db, lead_id, cursor=cursor, limit=limit
    )
    resolved: list[tuple[Activity, str | None]] = [
        (act, _resolve_author_name(act, name)) for (act, name) in rows
    ]
    return resolved, next_cursor
