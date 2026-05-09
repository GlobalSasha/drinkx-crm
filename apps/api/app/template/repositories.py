"""Message Templates data access — Sprint 2.4 G4."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.template.models import MessageTemplate


async def list_for_workspace(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    channel: str | None = None,
) -> list[MessageTemplate]:
    """All workspace templates, optionally filtered by channel.
    Newest first — admins typically edit recently-touched templates."""
    stmt = select(MessageTemplate).where(
        MessageTemplate.workspace_id == workspace_id
    )
    if channel is not None:
        stmt = stmt.where(MessageTemplate.channel == channel)
    stmt = stmt.order_by(MessageTemplate.updated_at.desc())
    res = await db.execute(stmt)
    return list(res.scalars().all())


async def get_by_id(
    db: AsyncSession,
    *,
    template_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> MessageTemplate | None:
    """Workspace-scoped fetch — returns None on cross-workspace lookup
    so the router maps to 404."""
    res = await db.execute(
        select(MessageTemplate).where(
            MessageTemplate.id == template_id,
            MessageTemplate.workspace_id == workspace_id,
        )
    )
    return res.scalar_one_or_none()


async def get_by_name_and_channel(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    name: str,
    channel: str,
) -> MessageTemplate | None:
    """Used by the service to detect duplicates before insert/update —
    surfaces a clean 409 instead of a DB integrity-error mid-transaction."""
    res = await db.execute(
        select(MessageTemplate).where(
            MessageTemplate.workspace_id == workspace_id,
            MessageTemplate.name == name,
            MessageTemplate.channel == channel,
        )
    )
    return res.scalar_one_or_none()


async def create(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    name: str,
    channel: str,
    category: str | None,
    text: str,
    created_by: uuid.UUID | None,
) -> MessageTemplate:
    row = MessageTemplate(
        workspace_id=workspace_id,
        name=name,
        channel=channel,
        category=category,
        text=text,
        created_by=created_by,
    )
    db.add(row)
    await db.flush()
    return row


async def update(
    db: AsyncSession,
    *,
    template: MessageTemplate,
    name: str | None,
    channel: str | None,
    category: str | None,
    text: str | None,
    category_set: bool = False,
) -> MessageTemplate:
    """In-place patch. None = leave field as-is, EXCEPT for `category`
    which is nullable — caller passes `category_set=True` to allow
    explicit clearing (None → NULL). Caller commits."""
    if name is not None:
        template.name = name
    if channel is not None:
        template.channel = channel
    if category_set:
        template.category = category
    if text is not None:
        template.text = text
    await db.flush()
    return template


async def delete(
    db: AsyncSession, *, template: MessageTemplate
) -> None:
    await db.delete(template)
    await db.flush()
