"""Reminder REST endpoints — personal sticky-notes (Today screen)."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.auth.models import User
from app.db import get_db
from app.reminders import services
from app.reminders.schemas import ReminderCreate, ReminderOut, ReminderUpdate

router = APIRouter(prefix="/api/reminders", tags=["reminders"])


@router.get("", response_model=list[ReminderOut])
async def list_reminders(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(current_user)],
) -> list[ReminderOut]:
    rows = await services.list_for_user(
        db, workspace_id=user.workspace_id, user_id=user.id
    )
    return [ReminderOut.model_validate(r) for r in rows]


@router.post("", response_model=ReminderOut, status_code=status.HTTP_201_CREATED)
async def create_reminder(
    payload: ReminderCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(current_user)],
) -> ReminderOut:
    row = await services.create(
        db, workspace_id=user.workspace_id, user_id=user.id, text=payload.text
    )
    await db.commit()
    return ReminderOut.model_validate(row)


@router.patch("/{reminder_id}", response_model=ReminderOut)
async def update_reminder(
    reminder_id: UUID,
    payload: ReminderUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(current_user)],
) -> ReminderOut:
    row = await services.update(
        db,
        workspace_id=user.workspace_id,
        user_id=user.id,
        reminder_id=reminder_id,
        text=payload.text,
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Reminder not found"
        )
    await db.commit()
    return ReminderOut.model_validate(row)


@router.delete("/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_reminder(
    reminder_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(current_user)],
) -> None:
    ok = await services.delete(
        db,
        workspace_id=user.workspace_id,
        user_id=user.id,
        reminder_id=reminder_id,
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Reminder not found"
        )
    await db.commit()
