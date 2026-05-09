"""Audit log data access — Sprint 1.5 + Sprint 2.4 G5 user-join.

`list_for_workspace_with_users` returns each AuditLog row paired with
the joined User's `name` + `email` (LEFT JOIN — `user_id` is nullable
for system-triggered events, and the inviter may have been deleted
since the action). Audit page renders «Имя · email@domain» when both
are present; falls back to first 8 chars of the raw user_id UUID
otherwise.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditLog
from app.auth.models import User


async def create(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    user_id: UUID | None,
    action: str,
    entity_type: str,
    entity_id: UUID | None,
    delta: dict | None,
) -> AuditLog:
    row = AuditLog(
        workspace_id=workspace_id,
        user_id=user_id,
        action=action,
        entity_type=entity_type or "",
        entity_id=entity_id,
        delta_json=delta,
    )
    session.add(row)
    await session.flush()
    return row


async def list_for_workspace(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[tuple[AuditLog, str | None, str | None]], int]:
    """Return (rows, total) ordered by created_at DESC.

    Each row is `(AuditLog, user_full_name, user_email)`. LEFT OUTER
    JOIN on `users.id = audit_logs.user_id` — system-triggered events
    or deleted users come back with both fields NULL, the router maps
    to the UUID-fallback rendering on the frontend.
    """
    base = (
        select(
            AuditLog,
            User.name.label("user_full_name"),
            User.email.label("user_email"),
        )
        .outerjoin(User, User.id == AuditLog.user_id)
        .where(AuditLog.workspace_id == workspace_id)
    )
    if entity_type is not None:
        base = base.where(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        base = base.where(AuditLog.entity_id == entity_id)

    # Count via the AuditLog query alone (the join is left-outer so it
    # doesn't change cardinality, but counting on a multi-column select
    # is cheaper if we strip down to just the audit-log id).
    count_stmt = (
        select(func.count(AuditLog.id))
        .where(AuditLog.workspace_id == workspace_id)
    )
    if entity_type is not None:
        count_stmt = count_stmt.where(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        count_stmt = count_stmt.where(AuditLog.entity_id == entity_id)

    total_result = await session.execute(count_stmt)
    total: int = int(total_result.scalar_one())

    rows_result = await session.execute(
        base.order_by(AuditLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows: list[tuple[AuditLog, str | None, str | None]] = [
        (row[0], row[1], row[2]) for row in rows_result.all()
    ]
    return rows, total
