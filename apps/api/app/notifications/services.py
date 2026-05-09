"""Notifications service layer — Sprint 1.5 + Sprint 2.5 G2 dedupe.

`notify()` is the single emit point. It only stages a row on the session
(`session.add()`) and flushes; it does NOT commit. The caller controls the
transaction boundary so notifications either land together with their
domain change or roll back together.

For best-effort emit from background tasks (orchestrator, cron, hook
exception path), wrap your `notify()` call in `_safe_notify()` — failures
are swallowed and logged, never bubbled up.

Sprint 2.5 G2 layered two suppression rules on top:

  1. **Empty `daily_plan_ready`.** When the daily plan generator
     produces zero items it still wants to ping the user, but waking
     them up to «у тебя нет задач сегодня» is noise. Detected by the
     body convention `"0 карточек, ..."` — daily_plan/services.py
     emits exactly this shape.

  2. **1h dedup window.** Same `(workspace_id, user_id, kind)` within
     the last hour → silent skip. Stops cron / fan-out flurries from
     drowning the bell. The exempt list is small and deliberate;
     `lead.urgent_signal` is the canonical example because by design
     it should reach the user every time.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Sequence
from uuid import UUID

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.notifications.models import Notification

log = structlog.get_logger()


# Kinds that bypass the 1h dedup window. These are «must reach the
# user» events; suppressing duplicates would defeat the purpose.
# Add new entries here in lock-step with the producing code path.
DEDUP_EXEMPT_KINDS: frozenset[str] = frozenset({
    "lead.urgent_signal",
})

DEDUP_WINDOW = timedelta(hours=1)

# `daily_plan_ready` body convention from `app.daily_plan.services` —
# `f"{len(orm_items)} карточек, ~{minutes} мин"`. Zero-items plans
# render as «0 карточек, ...» which is exactly what we want to skip.
_EMPTY_DAILY_PLAN_BODY_RE = re.compile(r"^\s*0\s+карточек\b")


async def _has_recent_same_kind(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    user_id: UUID,
    kind: str,
) -> bool:
    """Return True if the user already received a notification with
    this kind within DEDUP_WINDOW. Cheap existence check — uses the
    `(user_id, created_at)` index that the model already declares."""
    cutoff = datetime.now(tz=timezone.utc) - DEDUP_WINDOW
    res = await db.execute(
        select(Notification.id)
        .where(
            Notification.workspace_id == workspace_id,
            Notification.user_id == user_id,
            Notification.kind == kind,
            Notification.created_at > cutoff,
        )
        .limit(1)
    )
    return res.scalar_one_or_none() is not None


async def notify(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    user_id: UUID,
    kind: str,
    title: str,
    body: str = "",
    lead_id: UUID | None = None,
) -> Notification | None:
    """Stage a notification row on the current session. Caller commits.

    Returns None when the row is silently suppressed:
      - daily_plan_ready with empty body
      - same (workspace, user, kind) within the last hour, unless kind
        is in DEDUP_EXEMPT_KINDS

    The two suppression rules run BEFORE the row is staged — no
    «check after insert» pattern, no half-written rows on rollback.
    """
    # Rule 1: empty daily_plan_ready. Cheap string check — no DB hit.
    if kind == "daily_plan_ready" and _EMPTY_DAILY_PLAN_BODY_RE.match(
        body or ""
    ):
        log.info(
            "notifications.skip_empty_daily_plan",
            user_id=str(user_id),
        )
        return None

    # Rule 2: 1h dedup window. Skipped for exempt kinds — those are
    # «must always reach the user» events.
    if kind not in DEDUP_EXEMPT_KINDS:
        if await _has_recent_same_kind(
            db,
            workspace_id=workspace_id,
            user_id=user_id,
            kind=kind,
        ):
            log.info(
                "notifications.skip_dedup_window",
                kind=kind,
                user_id=str(user_id),
                window_hours=DEDUP_WINDOW.total_seconds() / 3600,
            )
            return None

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


async def dismiss(
    db: AsyncSession,
    *,
    notification_id: UUID,
    user_id: UUID,
) -> bool:
    """Hard-delete one notification row owned by this user (Sprint 2.4 G5).

    «Dismiss» is the persistent escape hatch for system / daily-plan
    rows that don't navigate to a lead — the manager can clear them
    without leaving stale «прочитано» rows around. Returns True when a
    row was removed; False on cross-user lookup or already-dismissed.
    Caller commits.
    """
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await db.delete(row)
    await db.flush()
    return True
