"""Contacts data-access layer — SQLAlchemy 2.0 async."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contacts.models import Contact


async def list_for_lead(db: AsyncSession, lead_id: uuid.UUID) -> list[Contact]:
    result = await db.execute(
        select(Contact).where(Contact.lead_id == lead_id).order_by(Contact.created_at.asc())
    )
    return list(result.scalars().all())


async def get_by_id(
    db: AsyncSession, contact_id: uuid.UUID, lead_id: uuid.UUID
) -> Contact | None:
    result = await db.execute(
        select(Contact).where(Contact.id == contact_id, Contact.lead_id == lead_id)
    )
    return result.scalar_one_or_none()


async def create(
    db: AsyncSession, lead_id: uuid.UUID, payload_dict: dict[str, Any]
) -> Contact:
    contact = Contact(lead_id=lead_id, **payload_dict)
    db.add(contact)
    await db.flush()
    await db.refresh(contact)
    return contact


async def update(
    db: AsyncSession, contact: Contact, patch_dict: dict[str, Any]
) -> Contact:
    for field, value in patch_dict.items():
        setattr(contact, field, value)
    await db.flush()
    await db.refresh(contact)
    return contact


async def delete(db: AsyncSession, contact: Contact) -> None:
    await db.delete(contact)
    await db.flush()
