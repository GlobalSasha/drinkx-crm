"""Contacts service layer — business validation on top of repositories."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.contacts import repositories as repo
from app.contacts.models import Contact, ContactRoleType, VerifiedStatus
from app.leads import repositories as leads_repo
from app.leads.services import LeadNotFound

_VALID_ROLE_TYPES = {r.value for r in ContactRoleType}
_VALID_VERIFIED_STATUSES = {v.value for v in VerifiedStatus}


class ContactNotFound(Exception):
    pass


def _validate_fields(role_type: str | None, verified_status: str | None) -> None:
    if role_type is not None and role_type not in _VALID_ROLE_TYPES:
        raise ValueError(f"Invalid role_type '{role_type}'. Allowed: {_VALID_ROLE_TYPES}")
    if verified_status is not None and verified_status not in _VALID_VERIFIED_STATUSES:
        raise ValueError(
            f"Invalid verified_status '{verified_status}'. Allowed: {_VALID_VERIFIED_STATUSES}"
        )


async def _get_lead_or_raise(
    db: AsyncSession, lead_id: uuid.UUID, workspace_id: uuid.UUID
) -> None:
    lead = await leads_repo.get_by_id(db, lead_id, workspace_id)
    if lead is None:
        raise LeadNotFound(lead_id)


async def list_contacts(
    db: AsyncSession, workspace_id: uuid.UUID, lead_id: uuid.UUID
) -> list[Contact]:
    await _get_lead_or_raise(db, lead_id, workspace_id)
    return await repo.list_for_lead(db, lead_id)


async def create_contact(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
    payload_dict: dict,
) -> Contact:
    await _get_lead_or_raise(db, lead_id, workspace_id)
    _validate_fields(payload_dict.get("role_type"), payload_dict.get("verified_status"))
    return await repo.create(db, lead_id, {**payload_dict, "workspace_id": workspace_id})


async def update_contact(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
    contact_id: uuid.UUID,
    patch_dict: dict,
) -> Contact:
    await _get_lead_or_raise(db, lead_id, workspace_id)
    contact = await repo.get_by_id(db, contact_id, lead_id)
    if contact is None:
        raise ContactNotFound(contact_id)
    _validate_fields(patch_dict.get("role_type"), patch_dict.get("verified_status"))
    return await repo.update(db, contact, patch_dict)


async def delete_contact(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
    contact_id: uuid.UUID,
) -> None:
    await _get_lead_or_raise(db, lead_id, workspace_id)
    contact = await repo.get_by_id(db, contact_id, lead_id)
    if contact is None:
        raise ContactNotFound(contact_id)
    await repo.delete(db, contact)
