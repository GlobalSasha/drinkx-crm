"""Activity service layer — business validation on top of repositories."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.activity import repositories as repo
from app.activity.models import Activity, ActivityType
from app.auth.models import User
from app.leads import repositories as leads_repo
from app.leads.services import LeadNotFound

_VALID_TYPES = {t.value for t in ActivityType}


class ActivityNotFound(Exception):
    pass


class ActivityWrongType(Exception):
    pass


class ActivityForbidden(Exception):
    """Caller is neither the activity's author nor an admin."""


def _validate_type(type_: str) -> None:
    if type_ not in _VALID_TYPES:
        raise ValueError(f"Invalid activity type '{type_}'. Allowed: {_VALID_TYPES}")


async def list_my_tasks(
    db: AsyncSession, *, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> list[dict]:
    """All manager-created tasks (Activity type=task) across leads
    assigned to the user. No AI — purely manual tasks. Ordered by due
    date ascending (nulls last), then newest first. Returns dicts
    shaped for MyTaskOut (text resolved from payload_json.title / body)."""
    from sqlalchemy import select

    from app.leads.models import Lead

    rows = (
        await db.execute(
            select(Activity, Lead.company_name)
            .join(Lead, Activity.lead_id == Lead.id)
            .where(
                Lead.workspace_id == workspace_id,
                Lead.assigned_to == user_id,
                Lead.archived_at.is_(None),
                Activity.type == ActivityType.task.value,
                Activity.archived_at.is_(None),
            )
            .order_by(
                Activity.task_due_at.asc().nulls_last(),
                Activity.created_at.desc(),
            )
            .limit(500)
        )
    ).all()

    out: list[dict] = []
    for activity, company_name in rows:
        text = (
            (activity.payload_json or {}).get("title")
            or activity.body
            or "Задача"
        )
        out.append(
            {
                "id": activity.id,
                "lead_id": activity.lead_id,
                "lead_company_name": company_name,
                "text": text,
                "task_due_at": activity.task_due_at,
                "task_done": activity.task_done,
                "task_completed_at": activity.task_completed_at,
                "created_at": activity.created_at,
            }
        )
    return out


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


async def update_task(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
    activity_id: uuid.UUID,
    *,
    body: str | None,
    task_due_at: datetime | None,
) -> Activity:
    """Update body and/or task_due_at on a task-Activity. Raises
    LeadNotFound / ActivityNotFound / ValueError if not a task."""
    if body is None and task_due_at is None:
        raise ValueError("at least one of body or task_due_at must be provided")
    await _get_lead_or_raise(db, lead_id, workspace_id)
    activity = await repo.get_by_id(db, activity_id, lead_id)
    if activity is None:
        raise ActivityNotFound(activity_id)
    if activity.type != ActivityType.task.value:
        raise ValueError("only task activities can be updated via this endpoint")
    if body is not None:
        cleaned = body.strip()
        if not cleaned:
            raise ValueError("body cannot be empty")
        activity.body = cleaned
        if activity.payload_json is None:
            activity.payload_json = {}
        activity.payload_json = {**activity.payload_json, "title": cleaned}
    if task_due_at is not None:
        activity.task_due_at = task_due_at
    await db.flush()
    await db.refresh(activity)
    return activity


async def update_comment(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
    activity_id: uuid.UUID,
    *,
    actor: User,
    body: str,
) -> Activity:
    """Edit the text of a manager comment. Only the comment's author or
    an admin may edit (mirrors the notes domain edit-own rule). Raises
    LeadNotFound / ActivityNotFound / ActivityForbidden / ValueError."""
    cleaned = body.strip()
    if not cleaned:
        raise ValueError("body cannot be empty")
    await _get_lead_or_raise(db, lead_id, workspace_id)
    activity = await repo.get_by_id(db, activity_id, lead_id)
    if activity is None:
        raise ActivityNotFound(activity_id)
    # Authorize BEFORE inspecting the row's type/shape — otherwise the
    # 404/400/403 status code becomes a within-workspace oracle that lets
    # a non-owner enumerate the existence and type of other managers'
    # activities. A non-owner always gets a uniform 403.
    if activity.user_id != actor.id and actor.role != "admin":
        raise ActivityForbidden(activity_id)
    if activity.type != ActivityType.comment.value:
        raise ValueError("only comment activities can be edited")
    # ask-Blake questions are AI-conversation turns paired with an answer
    # row; editing the question after the fact would desync the visible
    # Q/A. Keep them immutable.
    if (activity.payload_json or {}).get("source") == "ask_blake":
        raise ValueError("ask-Blake questions cannot be edited")
    activity.body = cleaned
    # Explicit edited flag (JSON column → no migration) so the feed can
    # mark «изменено» exactly, instead of guessing from timestamp deltas.
    activity.payload_json = {**(activity.payload_json or {}), "edited": True}
    await db.flush()
    await db.refresh(activity)
    return activity


async def archive_task(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
    activity_id: uuid.UUID,
) -> Activity:
    """Soft-archive a task-Activity. Sets archived_at = now() so the row is
    hidden from active views but preserved (with its file attachments) in the
    per-lead archive. File-attachment Activities are NOT cascade-archived;
    they remain visible under the archived task in the archive view."""
    await _get_lead_or_raise(db, lead_id, workspace_id)
    activity = await repo.get_by_id(db, activity_id, lead_id)
    if activity is None:
        raise ActivityNotFound(activity_id)
    if activity.type != ActivityType.task.value:
        raise ValueError("only task activities can be archived via this endpoint")
    if activity.archived_at is not None:
        return activity  # already archived — no-op (idempotent)
    activity.archived_at = datetime.now(timezone.utc)
    return activity


async def restore_task(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
    activity_id: uuid.UUID,
) -> Activity:
    """Restore an archived task. Sets archived_at = NULL."""
    await _get_lead_or_raise(db, lead_id, workspace_id)
    activity = await repo.get_by_id(db, activity_id, lead_id)
    if activity is None:
        raise ActivityNotFound(activity_id)
    if activity.type != ActivityType.task.value:
        raise ValueError("only task activities can be restored via this endpoint")
    activity.archived_at = None
    return activity


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


async def reopen_task(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
    activity_id: uuid.UUID,
) -> Activity:
    """Reopen a completed task so it returns to the active list."""
    await _get_lead_or_raise(db, lead_id, workspace_id)
    activity = await repo.get_by_id(db, activity_id, lead_id)
    if activity is None:
        raise ActivityNotFound(activity_id)
    if activity.type != ActivityType.task.value:
        raise ActivityWrongType("Cannot reopen non-task activity")
    if not activity.task_done:
        return activity  # idempotent
    return await repo.mark_task_open(db, activity)


# Author-name resolution for the unified feed. Anything written by the
# AI runner / chat handler is presented as «Блейк» regardless of the
# user_id stamped on the row (some chat answers carry the asking
# manager's id for audit; the visible author is still the AI).
_AI_AUTHOR_NAME = "Блейк"
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
