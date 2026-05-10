"""Followups service layer — business validation on top of repositories."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.followups import repositories as repo
from app.followups.models import Followup, FollowupStatus, ReminderKind
from app.followups.schemas import FollowupsPendingOut
from app.leads import repositories as leads_repo
from app.leads.services import LeadNotFound

_VALID_STATUSES = {s.value for s in FollowupStatus}
_VALID_REMINDER_KINDS = {r.value for r in ReminderKind}

DEFAULT_FOLLOWUPS: list[dict] = [
    {"name": "Первичный контакт",   "position": 0, "reminder_kind": "manager"},
    {"name": "Discovery-звонок",    "position": 1, "reminder_kind": "manager"},
    {"name": "Отправить материалы", "position": 2, "reminder_kind": "manager"},
]


class FollowupNotFound(Exception):
    pass


def _validate_fields(status: str | None, reminder_kind: str | None) -> None:
    if status is not None and status not in _VALID_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Allowed: {_VALID_STATUSES}")
    if reminder_kind is not None and reminder_kind not in _VALID_REMINDER_KINDS:
        raise ValueError(
            f"Invalid reminder_kind '{reminder_kind}'. Allowed: {_VALID_REMINDER_KINDS}"
        )


async def _get_lead_or_raise(
    db: AsyncSession, lead_id: uuid.UUID, workspace_id: uuid.UUID
) -> None:
    lead = await leads_repo.get_by_id(db, lead_id, workspace_id)
    if lead is None:
        raise LeadNotFound(lead_id)


async def list_followups(
    db: AsyncSession, workspace_id: uuid.UUID, lead_id: uuid.UUID
) -> list[Followup]:
    await _get_lead_or_raise(db, lead_id, workspace_id)
    return await repo.list_for_lead(db, lead_id)


async def create_followup(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
    payload_dict: dict,
) -> Followup:
    await _get_lead_or_raise(db, lead_id, workspace_id)
    _validate_fields(payload_dict.get("status"), payload_dict.get("reminder_kind"))
    return await repo.create(db, lead_id, payload_dict)


async def update_followup(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
    fu_id: uuid.UUID,
    patch_dict: dict,
) -> Followup:
    await _get_lead_or_raise(db, lead_id, workspace_id)
    fu = await repo.get_by_id(db, fu_id, lead_id)
    if fu is None:
        raise FollowupNotFound(fu_id)
    _validate_fields(patch_dict.get("status"), patch_dict.get("reminder_kind"))
    return await repo.update(db, fu, patch_dict)


async def delete_followup(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
    fu_id: uuid.UUID,
) -> None:
    await _get_lead_or_raise(db, lead_id, workspace_id)
    fu = await repo.get_by_id(db, fu_id, lead_id)
    if fu is None:
        raise FollowupNotFound(fu_id)
    await repo.delete(db, fu)


async def complete_followup(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
    fu_id: uuid.UUID,
) -> Followup:
    await _get_lead_or_raise(db, lead_id, workspace_id)
    fu = await repo.get_by_id(db, fu_id, lead_id)
    if fu is None:
        raise FollowupNotFound(fu_id)
    return await repo.update(
        db, fu, {"status": "done", "completed_at": datetime.now(timezone.utc)}
    )


async def seed_for_lead(db: AsyncSession, lead_id: uuid.UUID) -> None:
    await repo.bulk_seed_for_lead(db, lead_id, DEFAULT_FOLLOWUPS)


async def get_pending_counts_for_user(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> FollowupsPendingOut:
    """Aggregate counters for the Today follow-up widget — see repo."""
    pending, overdue = await repo.count_pending_for_user(
        db,
        user_id=user_id,
        workspace_id=workspace_id,
        now=datetime.now(timezone.utc),
    )
    return FollowupsPendingOut(pending_count=pending, overdue_count=overdue)
