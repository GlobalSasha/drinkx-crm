"""Followups data-access layer — SQLAlchemy 2.0 async."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.followups.models import Followup
from app.leads.models import Lead


async def list_for_lead(db: AsyncSession, lead_id: uuid.UUID) -> list[Followup]:
    result = await db.execute(
        select(Followup)
        .where(Followup.lead_id == lead_id)
        .order_by(Followup.position.asc(), Followup.created_at.asc())
    )
    return list(result.scalars().all())


async def get_by_id(
    db: AsyncSession, fu_id: uuid.UUID, lead_id: uuid.UUID
) -> Followup | None:
    result = await db.execute(
        select(Followup).where(Followup.id == fu_id, Followup.lead_id == lead_id)
    )
    return result.scalar_one_or_none()


async def create(
    db: AsyncSession, lead_id: uuid.UUID, payload_dict: dict[str, Any]
) -> Followup:
    fu = Followup(lead_id=lead_id, **payload_dict)
    db.add(fu)
    await db.flush()
    await db.refresh(fu)
    return fu


async def update(
    db: AsyncSession, fu: Followup, patch_dict: dict[str, Any]
) -> Followup:
    for field, value in patch_dict.items():
        setattr(fu, field, value)
    await db.flush()
    await db.refresh(fu)
    return fu


async def delete(db: AsyncSession, fu: Followup) -> None:
    await db.delete(fu)
    await db.flush()


async def bulk_seed_for_lead(
    db: AsyncSession, lead_id: uuid.UUID, defaults: list[dict[str, Any]]
) -> list[Followup]:
    created = []
    for d in defaults:
        fu = Followup(lead_id=lead_id, **d)
        db.add(fu)
        created.append(fu)
    await db.flush()
    for fu in created:
        await db.refresh(fu)
    return created


async def count_pending_for_user(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    workspace_id: uuid.UUID,
    now: datetime,
) -> tuple[int, int]:
    """Single-query counter for the Today follow-up widget.

    Returns (pending_count, overdue_count). One round-trip via the
    PostgreSQL `COUNT(*) FILTER (WHERE …)` aggregate.
    """
    cutoff_24h = now + timedelta(hours=24)
    pending_pred = and_(
        Followup.due_at.is_not(None),
        Followup.due_at <= cutoff_24h,
    )
    overdue_pred = and_(
        Followup.due_at.is_not(None),
        Followup.due_at < now,
    )
    stmt = (
        select(
            func.count().filter(pending_pred).label("pending"),
            func.count().filter(overdue_pred).label("overdue"),
        )
        .select_from(Followup)
        .join(Lead, Lead.id == Followup.lead_id)
        .where(
            Lead.assigned_to == user_id,
            Lead.workspace_id == workspace_id,
            Followup.status.in_(("pending", "active")),
        )
    )
    row = (await db.execute(stmt)).one()
    return int(row.pending), int(row.overdue)
