"""Reminder service layer — workspace + user scoped CRUD.

Tiny domain (no repository split): the three queries live here directly.
"""
from __future__ import annotations

import uuid

from sqlalchemy import delete as sa_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.reminders.models import Reminder

# Cap list size — the Today widget shows at most this many.
MAX_REMINDERS = 10


async def list_for_user(
    db: AsyncSession, *, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> list[Reminder]:
    res = await db.execute(
        select(Reminder)
        .where(
            Reminder.workspace_id == workspace_id,
            Reminder.user_id == user_id,
        )
        .order_by(Reminder.created_at.desc())
        .limit(MAX_REMINDERS)
    )
    return list(res.scalars().all())


async def create(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    text: str,
) -> Reminder:
    reminder = Reminder(
        workspace_id=workspace_id, user_id=user_id, text=text.strip()
    )
    db.add(reminder)
    await db.flush()
    return reminder


async def update(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    reminder_id: uuid.UUID,
    text: str,
) -> Reminder | None:
    """Edit the text of one reminder owned by the caller. Returns None if
    the row doesn't exist or belongs to someone else."""
    res = await db.execute(
        select(Reminder).where(
            Reminder.id == reminder_id,
            Reminder.workspace_id == workspace_id,
            Reminder.user_id == user_id,
        )
    )
    reminder = res.scalar_one_or_none()
    if reminder is None:
        return None
    reminder.text = text.strip()
    await db.flush()
    return reminder


async def delete(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    reminder_id: uuid.UUID,
) -> bool:
    """Hard-delete one reminder owned by the caller. Returns False if
    the row doesn't exist or belongs to someone else."""
    res = await db.execute(
        sa_delete(Reminder).where(
            Reminder.id == reminder_id,
            Reminder.workspace_id == workspace_id,
            Reminder.user_id == user_id,
        )
    )
    return res.rowcount > 0
