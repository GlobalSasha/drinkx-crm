"""Leads service layer — business validation on top of repositories."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User, Workspace
from app.automation.stage_change import (
    StageTransitionBlocked,
    StageTransitionInvalid,
    move_stage as automation_move_stage,
)
from app.leads import repositories as repo
from app.leads.models import DealType, Lead, Priority
from app.leads.schemas import LeadCreate, LeadUpdate
from app.pipelines.models import Stage


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


class StageNotFound(Exception):
    pass


# Re-export so callers can catch without importing from automation directly
__all__ = [
    "StageNotFound",
    "StageTransitionBlocked",
    "StageTransitionInvalid",
]


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
    patch = payload.model_dump(exclude_unset=True)
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
) -> tuple[list[Lead], int]:
    """Claim N leads from pool. Returns (claimed_leads, resolved_limit)."""
    if limit is None:
        ws_result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
        workspace = ws_result.scalar_one_or_none()
        if workspace is None:
            raise ValueError(f"Workspace {workspace_id} not found")
        limit = workspace.sprint_capacity_per_week

    items = await repo.claim_sprint(
        db,
        workspace_id,
        user_id,
        cities=cities,
        segment=segment,
        limit=limit,
    )
    return items, limit


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


async def move_lead_stage(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    lead_id: uuid.UUID,
    to_stage_id: uuid.UUID,
    gate_skipped: bool = False,
    skip_reason: str | None = None,
    lost_reason: str | None = None,
) -> Lead:
    lead = await repo.get_by_id(db, lead_id, workspace_id)
    if lead is None:
        raise LeadNotFound(lead_id)

    stage_result = await db.execute(select(Stage).where(Stage.id == to_stage_id))
    to_stage = stage_result.scalar_one_or_none()
    if to_stage is None:
        raise StageNotFound(to_stage_id)

    if lost_reason is not None:
        lead.lost_reason = lost_reason

    return await automation_move_stage(
        db, lead, to_stage, user_id,
        gate_skipped=gate_skipped, skip_reason=skip_reason,
    )
