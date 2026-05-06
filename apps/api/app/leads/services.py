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

# NOTE: app.followups.services is imported lazily inside create_lead() to avoid
# a module-level circular import (followups.services imports leads.services for
# LeadNotFound). With both top-level imports in place, load order becomes fragile.


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
    from app.followups import services as followups_services  # lazy: avoid circular import
    from app.pipelines import repositories as pipelines_repo

    _validate_enum_fields(payload.priority, payload.deal_type)
    data = payload.model_dump(exclude_none=False)

    # Default placement: position-0 stage of the workspace's default pipeline.
    # Without this, manager-created leads land in no column on the Kanban.
    if data.get("stage_id") is None and data.get("pipeline_id") is None:
        first = await pipelines_repo.get_default_first_stage(db, workspace_id)
        if first is not None:
            data["pipeline_id"], data["stage_id"] = first

    lead = await repo.create_lead(
        db,
        workspace_id,
        data,
        assigned_to=user_id,
        assignment_status="assigned",
    )
    await followups_services.seed_for_lead(db, lead.id)
    return lead


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
    """Move a lead to a new stage.

    Note: re-moving a won/lost lead is intentionally allowed — managers
    sometimes need to undo a mistakenly closed deal. The won_at/lost_at
    timestamps are preserved on re-entry (see `set_won_lost_timestamps`).
    """
    lead = await repo.get_by_id(db, lead_id, workspace_id)
    if lead is None:
        raise LeadNotFound(lead_id)

    # Workspace isolation: only allow stages whose pipeline belongs to this workspace.
    # Defends against cross-workspace stage moves when lead.pipeline_id is NULL
    # (which short-circuits the in-engine check_pipeline_match).
    from app.pipelines.models import Pipeline

    stage_result = await db.execute(
        select(Stage)
        .join(Pipeline, Stage.pipeline_id == Pipeline.id)
        .where(Stage.id == to_stage_id, Pipeline.workspace_id == workspace_id)
    )
    to_stage = stage_result.scalar_one_or_none()
    if to_stage is None:
        raise StageNotFound(to_stage_id)

    if lost_reason is not None:
        lead.lost_reason = lost_reason

    return await automation_move_stage(
        db, lead, to_stage, user_id,
        gate_skipped=gate_skipped, skip_reason=skip_reason,
    )
