"""Activity REST endpoints — nested under /leads/{lead_id}/activities."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.activity import repositories, services
from app.activity.schemas import (
    ActivityCreate,
    ActivityListOut,
    ActivityOut,
    AskBlakeIn,
    AskBlakeOut,
    CommentUpdateIn,
    FeedItemOut,
    FeedListOut,
    MyTaskOut,
    TaskUpdateIn,
)
from app.auth.dependencies import current_user
from app.auth.models import User
from app.db import get_db
from app.leads.services import LeadNotFound

router = APIRouter(prefix="/leads/{lead_id}/activities", tags=["activities"])

# Cross-lead aggregate for the manager's own tasks (Today widget +
# /tasks page). Not lead-scoped, so it sits on its own router.
me_router = APIRouter(tags=["activities"])


@me_router.get("/me/tasks", response_model=list[MyTaskOut])
async def list_my_tasks(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(current_user)],
) -> list[MyTaskOut]:
    """All manager-created tasks across the user's leads. Manager-only,
    no AI ordering."""
    rows = await services.list_my_tasks(
        db, workspace_id=user.workspace_id, user_id=user.id
    )
    return [MyTaskOut.model_validate(r) for r in rows]

# Separate router mounted at /leads/{lead_id}/feed — the unified
# activity feed (Sprint «Unified Activity Feed»). Lives in the same
# module because it shares the same service/repository layer.
feed_router = APIRouter(prefix="/leads/{lead_id}/feed", tags=["feed"])


def _to_feed_item(activity, author_name: str | None) -> FeedItemOut:
    # `from_attributes=True` on FeedItemOut pulls every column off the
    # Activity row; we attach author_name onto the instance so the same
    # pathway picks it up without a manual model_dump round-trip.
    activity.author_name = author_name  # type: ignore[attr-defined]
    return FeedItemOut.model_validate(activity, from_attributes=True)


@feed_router.get("", response_model=FeedListOut)
async def get_lead_feed(
    lead_id: UUID,
    cursor: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> FeedListOut:
    """Unified chronological feed for a lead — comments, tasks,
    calls, emails, AI suggestions, and system events in one stream.
    Cursor-paginated, newest-first."""
    try:
        rows, next_cursor = await services.list_feed(
            db, user.workspace_id, lead_id, cursor=cursor, limit=limit
        )
    except LeadNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    items = [_to_feed_item(act, name) for (act, name) in rows]
    return FeedListOut(
        items=items, next_cursor=next_cursor, has_more=next_cursor is not None
    )


@feed_router.post("/ask-blake", response_model=AskBlakeOut)
async def ask_blake(
    lead_id: UUID,
    payload: AskBlakeIn,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> AskBlakeOut:
    """Send a question to the lead-AI assistant (Блейк). The question
    is written into the feed as a `comment` from the asking manager;
    Блейк answer follows as an `ai_suggestion`. Both rows commit in
    one transaction so the feed never shows one without the other.

    Frontend appends the returned activities optimistically — no
    feed-wide refetch is needed for the round-trip."""
    from app.activity.models import Activity, ActivityType
    from app.lead_agent.runner import chat
    from app.lead_agent.tasks import _resolve_stage_name, select_lead_for_agent
    from sqlalchemy import select as sa_select

    # Verify the lead is in this workspace + load it for chat().
    try:
        await services._get_lead_or_raise(db, lead_id, user.workspace_id)
    except LeadNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")

    lead = (await db.execute(select_lead_for_agent(lead_id))).scalar_one_or_none()
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")

    stage_name = await _resolve_stage_name(db, lead)

    try:
        response = await chat(
            lead,
            payload.question,
            stage_name=stage_name,
            db=db,
            workspace_id=lead.workspace_id,
        )
    except Exception:
        # `chat` itself swallows LLMError and returns a polite Russian
        # fallback, so any exception here is unexpected (programmer
        # bug, network on Postgres mid-call, etc). Bubble as 502 so
        # the operator notices.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI assistant temporarily unavailable",
        )

    question_row = Activity(
        lead_id=lead_id,
        user_id=user.id,
        type=ActivityType.comment.value,
        body=payload.question,
        payload_json={"source": "ask_blake"},
    )
    answer_row = Activity(
        lead_id=lead_id,
        user_id=None,
        type=ActivityType.ai_suggestion.value,
        body=response.reply,
        payload_json={"source": "blake_chat"},
    )
    db.add(question_row)
    db.add(answer_row)
    await db.commit()
    await db.refresh(question_row)
    await db.refresh(answer_row)

    return AskBlakeOut(
        question_activity=_to_feed_item(question_row, user.name),
        answer_activity=_to_feed_item(answer_row, "Блейк"),
    )


@router.get("", response_model=ActivityListOut)
async def list_activities(
    lead_id: UUID,
    type: str | None = None,
    cursor: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> ActivityListOut:
    try:
        items, next_cursor = await services.list_activities(
            db, user.workspace_id, lead_id,
            type_filter=type,
            cursor=cursor,
            limit=limit,
        )
    except LeadNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    return ActivityListOut(items=items, next_cursor=next_cursor)  # type: ignore[arg-type]


@router.post("", response_model=ActivityOut, status_code=status.HTTP_201_CREATED)
async def create_activity(
    lead_id: UUID,
    payload: ActivityCreate,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> ActivityOut:
    try:
        activity = await services.create_activity(
            db, user.workspace_id, lead_id, user.id, payload.model_dump()
        )
    except LeadNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    await db.commit()
    return activity  # type: ignore[return-value]


@router.get("/archive", response_model=ActivityListOut)
async def list_archived(
    lead_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> ActivityListOut:
    """List archived (soft-deleted) activities for a lead. Ordered by archived_at desc."""
    try:
        await services._get_lead_or_raise(db, lead_id, user.workspace_id)
    except LeadNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="lead not found")
    rows = await repositories.list_archived_for_lead(db, lead_id=lead_id)
    return ActivityListOut(items=rows, next_cursor=None)  # type: ignore[arg-type]


@router.post("/{activity_id}/complete-task", response_model=ActivityOut)
async def complete_task(
    lead_id: UUID,
    activity_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> ActivityOut:
    try:
        activity = await services.complete_task(
            db, user.workspace_id, lead_id, activity_id, user.id
        )
    except LeadNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    except services.ActivityNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Activity not found")
    except services.ActivityWrongType as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    await db.commit()
    return activity  # type: ignore[return-value]


@router.post("/{activity_id}/reopen-task", response_model=ActivityOut)
async def reopen_task(
    lead_id: UUID,
    activity_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> ActivityOut:
    try:
        activity = await services.reopen_task(
            db, user.workspace_id, lead_id, activity_id
        )
    except LeadNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    except services.ActivityNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Activity not found")
    except services.ActivityWrongType as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    await db.commit()
    return activity  # type: ignore[return-value]


@router.patch("/{activity_id}", response_model=ActivityOut)
async def update_activity(
    lead_id: UUID,
    activity_id: UUID,
    payload: TaskUpdateIn,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> ActivityOut:
    try:
        activity = await services.update_task(
            db,
            workspace_id=user.workspace_id,
            lead_id=lead_id,
            activity_id=activity_id,
            body=payload.body,
            task_due_at=payload.task_due_at,
        )
    except LeadNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="lead not found")
    except services.ActivityNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    await db.commit()
    return activity  # type: ignore[return-value]


@router.patch("/{activity_id}/comment", response_model=ActivityOut)
async def update_comment(
    lead_id: UUID,
    activity_id: UUID,
    payload: CommentUpdateIn,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> ActivityOut:
    """Edit the text of a manager comment in the activity feed. Only the
    comment's author or an admin may edit."""
    try:
        activity = await services.update_comment(
            db,
            workspace_id=user.workspace_id,
            lead_id=lead_id,
            activity_id=activity_id,
            actor=user,
            body=payload.body,
        )
    except LeadNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="lead not found")
    except services.ActivityNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="comment not found")
    except services.ActivityForbidden:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the author or an admin can edit this comment",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    await db.commit()
    return activity  # type: ignore[return-value]


@router.delete("/{activity_id}", response_model=ActivityOut)
async def delete_activity(
    lead_id: UUID,
    activity_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> ActivityOut:
    """DELETE here means ARCHIVE — sets archived_at, preserves the row and
    its file attachments. Use POST /restore to undo."""
    try:
        activity = await services.archive_task(
            db,
            workspace_id=user.workspace_id,
            lead_id=lead_id,
            activity_id=activity_id,
        )
    except LeadNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="lead not found")
    except services.ActivityNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    await db.commit()
    return activity  # type: ignore[return-value]


@router.post("/{activity_id}/restore", response_model=ActivityOut)
async def restore_activity(
    lead_id: UUID,
    activity_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> ActivityOut:
    try:
        activity = await services.restore_task(
            db,
            workspace_id=user.workspace_id,
            lead_id=lead_id,
            activity_id=activity_id,
        )
    except LeadNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="lead not found")
    except services.ActivityNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    await db.commit()
    return activity  # type: ignore[return-value]
