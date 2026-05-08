"""Custom Attributes data access — Sprint 2.4 G3."""
from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.custom_attributes.models import (
    CustomAttributeDefinition,
    LeadCustomValue,
)


# ---------------------------------------------------------------------------
# Definitions
# ---------------------------------------------------------------------------

async def list_definitions(
    db: AsyncSession, *, workspace_id: uuid.UUID
) -> list[CustomAttributeDefinition]:
    """All definitions for the workspace, ordered by `position` then
    `key` for stable rendering when positions collide."""
    res = await db.execute(
        select(CustomAttributeDefinition)
        .where(CustomAttributeDefinition.workspace_id == workspace_id)
        .order_by(
            CustomAttributeDefinition.position.asc(),
            CustomAttributeDefinition.key.asc(),
        )
    )
    return list(res.scalars().all())


async def get_definition(
    db: AsyncSession,
    *,
    definition_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> CustomAttributeDefinition | None:
    """Workspace-scoped fetch. Returns None on cross-workspace lookup
    so the router maps to 404."""
    res = await db.execute(
        select(CustomAttributeDefinition).where(
            CustomAttributeDefinition.id == definition_id,
            CustomAttributeDefinition.workspace_id == workspace_id,
        )
    )
    return res.scalar_one_or_none()


async def get_by_key(
    db: AsyncSession, *, workspace_id: uuid.UUID, key: str
) -> CustomAttributeDefinition | None:
    res = await db.execute(
        select(CustomAttributeDefinition).where(
            CustomAttributeDefinition.workspace_id == workspace_id,
            CustomAttributeDefinition.key == key,
        )
    )
    return res.scalar_one_or_none()


async def next_position(
    db: AsyncSession, *, workspace_id: uuid.UUID
) -> int:
    """The next `position` to assign on create. MAX(position) + 1, or
    0 if the workspace has no definitions yet."""
    res = await db.execute(
        select(func.max(CustomAttributeDefinition.position)).where(
            CustomAttributeDefinition.workspace_id == workspace_id
        )
    )
    current = res.scalar_one_or_none()
    return 0 if current is None else int(current) + 1


async def create_definition(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    key: str,
    label: str,
    kind: str,
    options_json: list[dict] | None,
    is_required: bool,
    position: int,
) -> CustomAttributeDefinition:
    row = CustomAttributeDefinition(
        workspace_id=workspace_id,
        key=key,
        label=label,
        kind=kind,
        options_json=options_json,
        is_required=is_required,
        position=position,
    )
    db.add(row)
    await db.flush()
    return row


async def update_definition(
    db: AsyncSession,
    *,
    definition: CustomAttributeDefinition,
    label: str | None,
    options_json: list[dict] | None,
    is_required: bool | None,
    position: int | None,
) -> CustomAttributeDefinition:
    """In-place update. None = leave field as-is. Caller commits."""
    if label is not None:
        definition.label = label
    if options_json is not None:
        definition.options_json = options_json
    if is_required is not None:
        definition.is_required = is_required
    if position is not None:
        definition.position = position
    await db.flush()
    return definition


async def delete_definition(
    db: AsyncSession, *, definition: CustomAttributeDefinition
) -> None:
    """ON DELETE CASCADE on lead_custom_values handles value cleanup
    in the DB; we just drop the parent row."""
    await db.delete(definition)
    await db.flush()


# ---------------------------------------------------------------------------
# Values
# ---------------------------------------------------------------------------

async def get_value(
    db: AsyncSession,
    *,
    lead_id: uuid.UUID,
    definition_id: uuid.UUID,
) -> LeadCustomValue | None:
    res = await db.execute(
        select(LeadCustomValue).where(
            LeadCustomValue.lead_id == lead_id,
            LeadCustomValue.definition_id == definition_id,
        )
    )
    return res.scalar_one_or_none()


async def list_values_for_lead(
    db: AsyncSession, *, lead_id: uuid.UUID
) -> list[LeadCustomValue]:
    res = await db.execute(
        select(LeadCustomValue).where(LeadCustomValue.lead_id == lead_id)
    )
    return list(res.scalars().all())


async def upsert_value(
    db: AsyncSession,
    *,
    lead_id: uuid.UUID,
    definition_id: uuid.UUID,
    value_text: str | None = None,
    value_number: float | None = None,
    value_date=None,
) -> LeadCustomValue:
    """Create-or-update one (lead, definition) pair. Caller commits.

    The service is responsible for selecting the right typed argument
    based on the definition's `kind` — the repo just blindly writes
    whatever it's handed."""
    existing = await get_value(
        db, lead_id=lead_id, definition_id=definition_id
    )
    if existing is None:
        row = LeadCustomValue(
            lead_id=lead_id,
            definition_id=definition_id,
            value_text=value_text,
            value_number=value_number,
            value_date=value_date,
        )
        db.add(row)
        await db.flush()
        return row

    existing.value_text = value_text
    existing.value_number = value_number
    existing.value_date = value_date
    await db.flush()
    return existing


async def delete_value(
    db: AsyncSession,
    *,
    lead_id: uuid.UUID,
    definition_id: uuid.UUID,
) -> int:
    """Hard-delete one value row. Returns 1 if a row was removed, 0
    otherwise (idempotent — clearing an already-empty value is fine)."""
    res = await db.execute(
        delete(LeadCustomValue).where(
            LeadCustomValue.lead_id == lead_id,
            LeadCustomValue.definition_id == definition_id,
        )
    )
    return int(res.rowcount or 0)
