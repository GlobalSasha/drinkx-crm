"""Audit log data access — Sprint 1.5."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditLog


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
) -> tuple[list[AuditLog], int]:
    """Return (rows, total) ordered by created_at DESC."""
    base = select(AuditLog).where(AuditLog.workspace_id == workspace_id)
    if entity_type is not None:
        base = base.where(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        base = base.where(AuditLog.entity_id == entity_id)

    total_result = await session.execute(
        select(func.count()).select_from(base.subquery())
    )
    total: int = total_result.scalar_one()

    rows_result = await session.execute(
        base.order_by(AuditLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(rows_result.scalars().all()), total
