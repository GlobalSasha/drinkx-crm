"""Activity REST endpoints — nested under /leads/{lead_id}/activities."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.activity import services
from app.activity.schemas import ActivityCreate, ActivityListOut, ActivityOut
from app.auth.dependencies import current_user
from app.auth.models import User
from app.db import get_db
from app.leads.services import LeadNotFound

router = APIRouter(prefix="/leads/{lead_id}/activities", tags=["activities"])


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
