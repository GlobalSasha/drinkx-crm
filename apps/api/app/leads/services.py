"""Leads service layer — business validation on top of repositories."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User, Workspace
from app.leads import repositories as repo
from app.leads.models import DealType, Lead, Priority
from app.leads.schemas import LeadCreate, LeadUpdate


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class LeadNotFound(Exception):
    pass


class LeadAlreadyClaimed(Exception):
    pass


class LeadNotOwnedByUser(Exception):
    pass


class TransferTargetInvalid(Exception):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_PRIORITIES = {p.value for p in Priority}
_VALID_DEAL_TYPES = {d.value for d in DealType}


def _validate_enum_fields(priority: str | None, deal_type: str | None) -> None:
    if priority is not None and priority not in _VALID_PRIORITIES:
        raise ValueError(f"Invalid priority '{priority}'. Allowed: {_VALID_PRIORITIES}")
    if deal_type is not None and deal_type not in _VALID_DEAL_TYPES:
        raise ValueError(f"Invalid deal_type '{deal_type}'. Allowed: {_VALID_DEAL_TYPES}")


# ---------------------------------------------------------------------------
# Service functions
# ---------------------------------------------------------------------------

async def create_lead(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: LeadCreate,
) -> Lead:
    _validate_enum_fields(payload.priority, payload.deal_type)
    data = payload.model_dump(exclude_none=False)
    return await repo.create_lead(
        db,
        workspace_id,
        data,
        assigned_to=user_id,
        assignment_status="assigned",
    )


async def list_leads(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    filters: dict[str, Any],
) -> tuple[list[Lead], int]:
    return await repo.list_leads(db, workspace_id, **filters)


async def list_pool(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    filters: dict[str, Any],
) -> tuple[list[Lead], int]:
    return await repo.list_pool(db, workspace_id, **filters)


async def update_lead(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
    payload: LeadUpdate,
) -> Lead:
    lead = await repo.get_by_id(db, lead_id, workspace_id)
    if lead is None:
        raise LeadNotFound(lead_id)
    _validate_enum_fields(payload.priority, payload.deal_type)
    patch = {k: v for k, v in payload.model_dump().items() if v is not None}
    return await repo.update_lead(db, lead, patch)


async def delete_lead(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
) -> None:
    lead = await repo.get_by_id(db, lead_id, workspace_id)
    if lead is None:
        raise LeadNotFound(lead_id)
    await repo.delete_lead(db, lead)


async def claim_lead(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    lead_id: uuid.UUID,
) -> Lead:
    lead = await repo.claim_lead(db, lead_id, workspace_id, user_id)
    if lead is None:
        raise LeadAlreadyClaimed(lead_id)
    return lead


async def claim_sprint(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    cities: list[str],
    segment: str | None,
    limit: int | None,
) -> list[Lead]:
    if limit is None:
        ws_result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
        workspace = ws_result.scalar_one_or_none()
        limit = workspace.sprint_capacity_per_week if workspace else 20

    return await repo.claim_sprint(
        db,
        workspace_id,
        user_id,
        cities=cities,
        segment=segment,
        limit=limit,
    )


async def transfer_lead(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    current_user_id: uuid.UUID,
    current_user_role: str,
    lead_id: uuid.UUID,
    to_user_id: uuid.UUID,
    comment: str | None,
) -> Lead:
    lead = await repo.get_by_id(db, lead_id, workspace_id)
    if lead is None:
        raise LeadNotFound(lead_id)

    # Ownership check: must be assigned to current user OR current user is admin/head
    is_privileged = current_user_role in ("admin", "head")
    if lead.assigned_to != current_user_id and not is_privileged:
        raise LeadNotOwnedByUser(lead_id)

    # Validate target user is in the same workspace
    target_result = await db.execute(
        select(User).where(User.id == to_user_id, User.workspace_id == workspace_id)
    )
    target = target_result.scalar_one_or_none()
    if target is None:
        raise TransferTargetInvalid(to_user_id)

    return await repo.transfer_lead(db, lead, to_user_id, comment=comment)
