"""Contacts REST endpoints — nested under /leads/{lead_id}/contacts."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.auth.models import User
from app.contacts import services
from app.contacts.schemas import ContactCreate, ContactOut, ContactUpdate
from app.db import get_db
from app.leads.services import LeadNotFound

router = APIRouter(prefix="/leads/{lead_id}/contacts", tags=["contacts"])


@router.get("", response_model=list[ContactOut])
async def list_contacts(
    lead_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> list[ContactOut]:
    try:
        contacts = await services.list_contacts(db, user.workspace_id, lead_id)
    except LeadNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    return contacts  # type: ignore[return-value]


@router.post("", response_model=ContactOut, status_code=status.HTTP_201_CREATED)
async def create_contact(
    lead_id: UUID,
    payload: ContactCreate,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> ContactOut:
    try:
        contact = await services.create_contact(
            db, user.workspace_id, lead_id, payload.model_dump()
        )
    except LeadNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    await db.commit()
    return contact  # type: ignore[return-value]


@router.patch("/{contact_id}", response_model=ContactOut)
async def update_contact(
    lead_id: UUID,
    contact_id: UUID,
    payload: ContactUpdate,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> ContactOut:
    try:
        contact = await services.update_contact(
            db, user.workspace_id, lead_id, contact_id,
            payload.model_dump(exclude_unset=True),
        )
    except LeadNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    except services.ContactNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    await db.commit()
    return contact  # type: ignore[return-value]


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(
    lead_id: UUID,
    contact_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> None:
    try:
        await services.delete_contact(db, user.workspace_id, lead_id, contact_id)
    except LeadNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    except services.ContactNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    await db.commit()
