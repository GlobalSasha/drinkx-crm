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


class PrimaryContactInvalid(Exception):
    """Raised when the requested contact doesn't exist or doesn't belong
    to the target lead."""


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

async def get_lead(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
) -> Lead:
    """Fetch one lead, scoped to workspace. Raises LeadNotFound otherwise.

    Used by endpoints (e.g. /leads/{id}/attributes) that need workspace
    isolation but don't want to duplicate the 404-or-Lead branching.
    """
    lead = await repo.get_by_id(db, lead_id, workspace_id)
    if lead is None:
        raise LeadNotFound(lead_id)
    return lead


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

    # Sprint 3.3 — when payload carries `company_id`, replace
    # `company_name` with the authoritative `companies.name` so the
    # snapshot is correct from t=0 (ADR-022).
    if data.get("company_id") is not None:
        from app.companies.repositories import get_by_id as _get_company

        company = await _get_company(
            db, workspace_id=workspace_id, company_id=data["company_id"]
        )
        if company is not None:
            data["company_name"] = company.name

    lead = await repo.create_lead(
        db,
        workspace_id,
        data,
        assigned_to=user_id,
        assignment_status="assigned",
    )
    await followups_services.seed_for_lead(db, lead.id)

    # Audit: lead.create
    from app.audit.audit import log as audit_log

    await audit_log(
        db,
        action="lead.create",
        workspace_id=workspace_id,
        user_id=user_id,
        entity_type="lead",
        entity_id=lead.id,
        delta={
            "company_name": lead.company_name,
            "stage_id": str(lead.stage_id) if lead.stage_id else None,
        },
    )
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


class CompanyNameLocked(Exception):
    """Sprint 3.3: direct edit of `company_name` is rejected when the
    lead is linked to a company. The frontend renames via PATCH
    /companies/{id} instead, which then propagates to active leads."""


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
    # ADR-022 sync rule: company_name is a snapshot; rename a linked
    # lead's name only via the company-rename code path.
    if "company_name" in patch and lead.company_id is not None:
        raise CompanyNameLocked()
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


async def unclaim_lead(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    lead_id: uuid.UUID,
) -> Lead:
    """Return an assigned lead to the pool. Caller must own it (or be
    privileged — admins/heads can re-pool any lead). Raises
    LeadNotFound if the lead doesn't exist in the workspace, or
    LeadNotOwnedByUser if it's owned by a different manager."""
    existing = await repo.get_by_id(db, lead_id, workspace_id)
    if existing is None:
        raise LeadNotFound(lead_id)
    if existing.assigned_to != user_id:
        raise LeadNotOwnedByUser(lead_id)
    lead = await repo.unclaim_lead(db, lead_id, workspace_id, user_id)
    if lead is None:
        # Race: ownership was valid at the read above but flipped before
        # the atomic UPDATE. Surface as «not owned» — same shape the
        # caller already handles for the static-check failure.
        raise LeadNotOwnedByUser(lead_id)
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

    old_assigned_to = lead.assigned_to
    transferred = await repo.transfer_lead(db, lead, to_user_id, comment=comment)

    # Notify the new owner. Same transaction as the transfer — rolls back together.
    from app.notifications.services import safe_notify

    company = transferred.company_name or "—"
    body = comment or "Лид передан вам"
    await safe_notify(
        db,
        workspace_id=workspace_id,
        user_id=to_user_id,
        kind="lead_transferred",
        title=f"Передан лид: {company}",
        body=body,
        lead_id=transferred.id,
    )

    # Audit: lead.transfer
    from app.audit.audit import log as audit_log

    await audit_log(
        db,
        action="lead.transfer",
        workspace_id=workspace_id,
        user_id=current_user_id,
        entity_type="lead",
        entity_id=transferred.id,
        delta={
            "from": str(old_assigned_to) if old_assigned_to else None,
            "to": str(to_user_id),
        },
    )
    return transferred


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

    from_stage_id = lead.stage_id
    moved = await automation_move_stage(
        db, lead, to_stage, user_id,
        gate_skipped=gate_skipped, skip_reason=skip_reason,
    )

    # Audit: lead.move_stage (only on successful transition — exceptions
    # bubble out before this point and the row was never touched)
    from app.audit.audit import log as audit_log

    await audit_log(
        db,
        action="lead.move_stage",
        workspace_id=workspace_id,
        user_id=user_id,
        entity_type="lead",
        entity_id=moved.id,
        delta={
            "from_stage": str(from_stage_id) if from_stage_id else None,
            "to_stage": str(to_stage_id),
        },
    )
    return moved


async def set_primary_contact(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
    contact_id: uuid.UUID | None,
) -> Lead:
    """Singled-out «основной ЛПР» on a lead. Pass None to clear.

    `contact_id` (when set) must point to a Contact attached to this
    very lead — cross-lead reuse is rejected so a manager can't
    accidentally promote someone else's contact via UUID forgery.
    """
    from app.contacts.models import Contact

    lead = await repo.get_by_id(db, lead_id, workspace_id)
    if lead is None:
        raise LeadNotFound(lead_id)

    if contact_id is not None:
        result = await db.execute(
            select(Contact).where(
                Contact.id == contact_id,
                Contact.lead_id == lead_id,
            )
        )
        if result.scalar_one_or_none() is None:
            raise PrimaryContactInvalid(contact_id)

    lead.primary_contact_id = contact_id
    await db.commit()
    # Re-fetch so the response carries the joined primary_contact_name
    # and the open-counts subqueries.
    refreshed = await repo.get_by_id(db, lead_id, workspace_id)
    assert refreshed is not None
    return refreshed
