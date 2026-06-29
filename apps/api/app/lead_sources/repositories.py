"""Data access for the lead-source dictionary."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.lead_sources.models import DEFAULT_LEAD_SOURCES, LeadSource


async def list_sources(
    db: AsyncSession, *, workspace_id: uuid.UUID, active_only: bool = False
) -> list[LeadSource]:
    stmt = select(LeadSource).where(LeadSource.workspace_id == workspace_id)
    if active_only:
        stmt = stmt.where(LeadSource.is_active.is_(True))
    stmt = stmt.order_by(LeadSource.sort_order, LeadSource.name)
    return list((await db.execute(stmt)).scalars().all())


async def get_source(
    db: AsyncSession, *, source_id: uuid.UUID, workspace_id: uuid.UUID
) -> LeadSource | None:
    stmt = select(LeadSource).where(
        LeadSource.id == source_id, LeadSource.workspace_id == workspace_id
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_by_name(
    db: AsyncSession, *, workspace_id: uuid.UUID, name: str
) -> LeadSource | None:
    stmt = select(LeadSource).where(
        LeadSource.workspace_id == workspace_id, LeadSource.name == name
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def create_source(db: AsyncSession, source: LeadSource) -> LeadSource:
    db.add(source)
    await db.flush()
    return source


async def seed_defaults(db: AsyncSession, *, workspace_id: uuid.UUID) -> int:
    """Insert the default sources for a workspace, skipping names already present.

    Idempotent — safe to call on bootstrap and on already-seeded workspaces.
    Returns the count of newly inserted rows.
    """
    existing = {s.name for s in await list_sources(db, workspace_id=workspace_id)}
    created = 0
    for seed in DEFAULT_LEAD_SOURCES:
        if seed["name"] in existing:
            continue
        db.add(LeadSource(workspace_id=workspace_id, **seed))
        created += 1
    if created:
        await db.flush()
    return created
