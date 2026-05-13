"""Leads data-access layer — SQLAlchemy 2.0 async."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, nullslast, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.leads.models import Lead


async def get_by_id(db: AsyncSession, lead_id: uuid.UUID, workspace_id: uuid.UUID) -> Lead | None:
    result = await db.execute(
        select(Lead).where(Lead.id == lead_id, Lead.workspace_id == workspace_id)
    )
    return result.scalar_one_or_none()


async def list_leads(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    *,
    stage_id: uuid.UUID | None = None,
    pipeline_id: uuid.UUID | None = None,
    segment: str | None = None,
    city: str | None = None,
    priority: str | None = None,
    deal_type: str | None = None,
    assigned_to: uuid.UUID | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[Lead], int]:
    """Return (rows, total) — only assignment_status='assigned' leads.

    Sprint 2.3 G2: pipeline_id filter scopes the result set to one
    voronka. The /pipeline switcher passes the user-selected pipeline
    id; /today and /leads-pool intentionally don't filter and keep
    aggregating across all of the user's pipelines.
    """
    base = select(Lead).where(
        Lead.workspace_id == workspace_id,
        Lead.assignment_status == "assigned",
    )
    if stage_id is not None:
        base = base.where(Lead.stage_id == stage_id)
    if pipeline_id is not None:
        base = base.where(Lead.pipeline_id == pipeline_id)
    if segment is not None:
        base = base.where(Lead.segment == segment)
    if city is not None:
        base = base.where(Lead.city == city)
    if priority is not None:
        base = base.where(Lead.priority == priority)
    if deal_type is not None:
        base = base.where(Lead.deal_type == deal_type)
    if assigned_to is not None:
        base = base.where(Lead.assigned_to == assigned_to)
    if q is not None:
        base = base.where(Lead.company_name.ilike(f"%{q}%"))

    count_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total: int = count_result.scalar_one()

    rows_result = await db.execute(
        base.order_by(Lead.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(rows_result.scalars().all()), total


async def list_pool(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    *,
    city: str | None = None,
    segment: str | None = None,
    fit_min: float | None = None,
    priority: str | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[Lead], int]:
    """Return pool leads ordered by fit_score DESC NULLS LAST, created_at ASC."""
    base = select(Lead).where(
        Lead.workspace_id == workspace_id,
        Lead.assignment_status == "pool",
    )
    if city is not None:
        base = base.where(Lead.city.ilike(f"%{city}%"))
    if segment is not None:
        base = base.where(Lead.segment == segment)
    if fit_min is not None:
        base = base.where(Lead.fit_score >= fit_min)
    if priority is not None:
        base = base.where(Lead.priority == priority)
    if q is not None:
        base = base.where(Lead.company_name.ilike(f"%{q}%"))

    count_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total: int = count_result.scalar_one()

    rows_result = await db.execute(
        base.order_by(nullslast(Lead.fit_score.desc()), Lead.created_at.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(rows_result.scalars().all()), total


async def create_lead(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    payload: dict[str, Any],
    *,
    assigned_to: uuid.UUID | None = None,
    assignment_status: str = "assigned",
) -> Lead:
    now = datetime.now(timezone.utc)
    lead = Lead(
        workspace_id=workspace_id,
        assignment_status=assignment_status,
        assigned_to=assigned_to,
        assigned_at=now if assigned_to else None,
        **payload,
    )
    db.add(lead)
    await db.flush()
    await db.refresh(lead)
    return lead


async def update_lead(db: AsyncSession, lead: Lead, patch_dict: dict[str, Any]) -> Lead:
    for field, value in patch_dict.items():
        setattr(lead, field, value)
    await db.flush()
    await db.refresh(lead)
    return lead


async def delete_lead(db: AsyncSession, lead: Lead) -> None:
    await db.delete(lead)
    await db.flush()


async def claim_lead(
    db: AsyncSession,
    lead_id: uuid.UUID,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Lead | None:
    """Race-safe atomic UPDATE — returns None if already claimed."""
    stmt = (
        update(Lead)
        .where(
            Lead.id == lead_id,
            Lead.workspace_id == workspace_id,
            Lead.assignment_status == "pool",
        )
        .values(
            assigned_to=user_id,
            assigned_at=func.now(),
            assignment_status="assigned",
        )
        .returning(Lead)
    )
    result = await db.execute(stmt)
    await db.flush()
    return result.scalar_one_or_none()


async def unclaim_lead(
    db: AsyncSession,
    lead_id: uuid.UUID,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Lead | None:
    """Atomic UPDATE that returns a lead to the pool. Returns None if the
    lead isn't assigned to `user_id` (so callers can surface a 403/404).
    """
    stmt = (
        update(Lead)
        .where(
            Lead.id == lead_id,
            Lead.workspace_id == workspace_id,
            Lead.assigned_to == user_id,
            Lead.assignment_status == "assigned",
        )
        .values(
            assigned_to=None,
            assigned_at=None,
            assignment_status="pool",
        )
        .returning(Lead)
    )
    result = await db.execute(stmt)
    await db.flush()
    return result.scalar_one_or_none()


async def claim_sprint(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    cities: list[str],
    segment: str | None = None,
    limit: int = 20,
) -> list[Lead]:
    """Race-safe N-claim using FOR UPDATE SKIP LOCKED."""
    # Step 1: select candidate IDs (SKIP LOCKED avoids blocking concurrent sprints)
    where_parts = [
        "workspace_id = :workspace_id",
        "assignment_status = 'pool'",
    ]
    params: dict[str, Any] = {"workspace_id": workspace_id, "limit": limit}

    if cities:
        where_parts.append("city = ANY(:cities)")
        params["cities"] = cities

    if segment is not None:
        where_parts.append("segment = :segment")
        params["segment"] = segment

    where_clause = " AND ".join(where_parts)
    sql = text(
        f"SELECT id FROM leads WHERE {where_clause} "
        "ORDER BY fit_score DESC NULLS LAST, created_at ASC "
        "LIMIT :limit FOR UPDATE SKIP LOCKED"
    )
    id_result = await db.execute(sql, params)
    candidate_ids = [row[0] for row in id_result.fetchall()]

    # Step 2: claim each candidate individually (only if still pool)
    claimed: list[Lead] = []
    for lead_id in candidate_ids:
        stmt = (
            update(Lead)
            .where(Lead.id == lead_id, Lead.assignment_status == "pool")
            .values(
                assigned_to=user_id,
                assigned_at=func.now(),
                assignment_status="assigned",
            )
            .returning(Lead)
        )
        result = await db.execute(stmt)
        lead = result.scalar_one_or_none()
        if lead is not None:
            claimed.append(lead)

    await db.flush()
    return claimed


async def transfer_lead(
    db: AsyncSession,
    lead: Lead,
    to_user_id: uuid.UUID,
    comment: str | None = None,  # noqa: ARG001 — stored in activity log (Task 4)
) -> Lead:
    """Transfer ownership, recording the previous assignee."""
    now = datetime.now(timezone.utc)
    lead.transferred_from = lead.assigned_to
    lead.transferred_at = now
    lead.assigned_to = to_user_id
    lead.assigned_at = now
    lead.assignment_status = "assigned"
    await db.flush()
    await db.refresh(lead)
    return lead
