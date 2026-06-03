"""UTM find-or-create — Odoo `utm.mixin._get_unique_names` pattern.

Resolve inbound UTM param strings into per-workspace dictionary rows, creating
them on first sight (marked `is_auto=True`). Returns the resolved ids so the
caller can stamp them onto the lead for queryable attribution.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.utm.models import UtmCampaign, UtmMedium, UtmSource


def _clean(name: str | None) -> str | None:
    """Trim + cap length; empty/whitespace → None (no dictionary row)."""
    if not name:
        return None
    cleaned = name.strip()[:120].strip()
    return cleaned or None


async def _find_or_create(
    session: AsyncSession, model, workspace_id: uuid.UUID, name: str | None
) -> uuid.UUID | None:
    name = _clean(name)
    if name is None:
        return None
    existing = (
        await session.execute(
            select(model).where(model.workspace_id == workspace_id, model.name == name).limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing.id
    row = model(workspace_id=workspace_id, name=name, is_auto=True)
    session.add(row)
    await session.flush()
    return row.id


async def resolve_utm(
    session: AsyncSession, workspace_id: uuid.UUID, utm: dict[str, str]
) -> dict[str, uuid.UUID | None]:
    """Resolve utm_source / utm_medium / utm_campaign names to dictionary ids.

    Missing or blank params resolve to None. Caller commits the session.
    """
    return {
        "utm_source_id": await _find_or_create(session, UtmSource, workspace_id, utm.get("utm_source")),
        "utm_medium_id": await _find_or_create(session, UtmMedium, workspace_id, utm.get("utm_medium")),
        "utm_campaign_id": await _find_or_create(session, UtmCampaign, workspace_id, utm.get("utm_campaign")),
    }
