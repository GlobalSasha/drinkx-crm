"""Notifications REST endpoints — Sprint 1.5."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.auth.models import User
from app.db import get_db
from app.notifications import services
from app.notifications.schemas import (
    MarkAllReadOut,
    NotificationListOut,
    NotificationOut,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListOut)
async def list_notifications(
    unread: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> NotificationListOut:
    items, total, unread_count = await services.list_for_user(
        db,
        user_id=user.id,
        unread=unread,
        page=page,
        page_size=page_size,
    )
    return NotificationListOut(
        items=[NotificationOut.model_validate(i) for i in items],
        total=total,
        unread=unread_count,
        page=page,
        page_size=page_size,
    )


@router.post("/{notification_id}/read", response_model=NotificationOut)
async def mark_one_read(
    notification_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> NotificationOut:
    row = await services.mark_read(db, notification_id=notification_id, user_id=user.id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )
    await db.commit()
    return NotificationOut.model_validate(row)


@router.post("/mark-all-read", response_model=MarkAllReadOut)
async def mark_all_read(
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> MarkAllReadOut:
    affected = await services.mark_all_read(db, user_id=user.id)
    await db.commit()
    return MarkAllReadOut(affected=affected)


@router.delete(
    "/{notification_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def dismiss_notification(
    notification_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> None:
    """Permanent dismiss for system / daily-plan rows (Sprint 2.4 G5).

    Distinguished from «mark as read» — read items still occupy drawer
    space when «Все» is selected. Dismiss is hard-delete, scoped to
    the caller's own rows.
    """
    ok = await services.dismiss(
        db, notification_id=notification_id, user_id=user.id
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )
    await db.commit()
