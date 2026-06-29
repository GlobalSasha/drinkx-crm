"""Business logic for the lead-source dictionary."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.lead_sources import repositories as repo
from app.lead_sources.models import LeadSource
from app.lead_sources.schemas import LeadSourceCreateIn, LeadSourceUpdateIn


class LeadSourceNotFound(Exception):
    pass


class LeadSourceNameConflict(Exception):
    """A source with this name already exists in the workspace."""


class LeadSourceIsSystem(Exception):
    """System sources (Яндекс Директ, Сайт) cannot be deleted."""


async def list_sources(
    db: AsyncSession, *, workspace_id: uuid.UUID, active_only: bool = False
) -> list[LeadSource]:
    return await repo.list_sources(db, workspace_id=workspace_id, active_only=active_only)


async def create_source(
    db: AsyncSession, *, workspace_id: uuid.UUID, payload: LeadSourceCreateIn
) -> LeadSource:
    name = payload.name.strip()
    if await repo.get_by_name(db, workspace_id=workspace_id, name=name):
        raise LeadSourceNameConflict(name)
    source = LeadSource(
        workspace_id=workspace_id,
        name=name,
        is_paid=payload.is_paid,
        sort_order=payload.sort_order,
        is_system=False,
    )
    return await repo.create_source(db, source)


async def update_source(
    db: AsyncSession,
    *,
    source_id: uuid.UUID,
    workspace_id: uuid.UUID,
    payload: LeadSourceUpdateIn,
) -> LeadSource:
    source = await repo.get_source(db, source_id=source_id, workspace_id=workspace_id)
    if source is None:
        raise LeadSourceNotFound(source_id)

    if payload.name is not None:
        name = payload.name.strip()
        if name != source.name:
            clash = await repo.get_by_name(db, workspace_id=workspace_id, name=name)
            if clash is not None and clash.id != source.id:
                raise LeadSourceNameConflict(name)
        source.name = name
    if payload.is_active is not None:
        source.is_active = payload.is_active
    if payload.is_paid is not None:
        source.is_paid = payload.is_paid
    if payload.sort_order is not None:
        source.sort_order = payload.sort_order

    await db.flush()
    return source


async def delete_source(
    db: AsyncSession, *, source_id: uuid.UUID, workspace_id: uuid.UUID
) -> None:
    source = await repo.get_source(db, source_id=source_id, workspace_id=workspace_id)
    if source is None:
        raise LeadSourceNotFound(source_id)
    if source.is_system:
        raise LeadSourceIsSystem(source_id)
    await db.delete(source)
    await db.flush()
