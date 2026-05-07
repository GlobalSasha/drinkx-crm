"""Notifications service layer — Sprint 1.5.

`notify()` is the single emit point. It only stages a row on the session
(`session.add()`) and flushes; it does NOT commit. The caller controls the
transaction boundary so notifications either land together with their
domain change or roll back together.

For best-effort emit from background tasks (orchestrator, cron, hook
exception path), wrap your `notify()` call in `_safe_notify()` — failures
are swallowed and logged, never bubbled up.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Sequence
from uuid import UUID

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.notifications.models import Notification

log = structlog.get_logger()


async def notify(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    user_id: UUID,
    kind: str,
    title: str,
    body: str = "",
    lead_id: UUID | None = None,
) -> Notification:
    """Stage a notification row on the current session. Caller commits."""
    row = Notification(
        workspace_id=workspace_id,
        user_id=user_id,
        kind=kind,
        title=title[:200],
        body=body or "",
        lead_id=lead_id,
    )
    db.add(row)
    await db.flush()
    return row


async def safe_notify(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    user_id: UUID,
    kind: str,
    title: str,
    body: str = "",
    lead_id: UUID | None = None,
) -> Notification | None:
    """Best-effort wrapper — never raises. Use from cron/orchestrator paths."""
    try:
        return await notify(
            db,
            workspace_id=workspace_id,
            user_id=user_id,
            kind=kind,
            title=title,
            body=body,
            lead_id=lead_id,
        )
    except Exception as exc:
        log.warning(
            "notifications.emit_failed",
            kind=kind,
            user_id=str(user_id),
            error=str(exc)[:200],
        )
        return None


# ---------------------------------------------------------------------------
# Read-side
# ---------------------------------------------------------------------------

async def list_for_user(
    db: AsyncSession,
    *,
    user_id: UUID,
    unread: bool = False,
    page: int = 1,
    page_size: int = 30,
) -> tuple[list[Notification], int, int]:
    """Return (items, total_matched, unread_count)."""
    base = select(Notification).where(Notification.user_id == user_id)
    if unread:
        base = base.where(Notification.read_at.is_(None))

    total_result = await db.execute(
        select(func.count()).select_from(base.subquery())
    )
    total: int = total_result.scalar_one()

    unread_result = await db.execute(
        select(func.count()).where(
            Notification.user_id == user_id,
            Notification.read_at.is_(None),
        )
    )
    unread_count: int = unread_result.scalar_one()

    rows_result = await db.execute(
        base.order_by(Notification.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list(rows_result.scalars().all())
    return items, total, unread_count


async def mark_read(
    db: AsyncSession,
    *,
    notification_id: UUID,
    user_id: UUID,
) -> Notification | None:
    """Mark one row read. Returns None if the row belongs to another user
    (cross-user mutation guard) or doesn't exist."""
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    if row.read_at is None:
        row.read_at = datetime.now(tz=timezone.utc)
        await db.flush()
    return row


async def mark_all_read(
    db: AsyncSession,
    *,
    user_id: UUID,
) -> int:
    """Mark every unread notification for this user as read. Returns count."""
    now = datetime.now(tz=timezone.utc)
    result = await db.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        .values(read_at=now)
    )
    affected = result.rowcount or 0
    await db.flush()
    return int(affected)
