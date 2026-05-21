"""LeadNote REST endpoints — nested under /leads/{lead_id}/notes."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.auth.models import User
from app.db import get_db
from app.notes import services
from app.notes.schemas import NoteCreate, NoteOut, NoteUpdate

router = APIRouter(prefix="/leads/{lead_id}/notes", tags=["notes"])


@router.get("", response_model=list[NoteOut])
async def list_notes(
    lead_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> list[NoteOut]:
    try:
        rows = await services.list_for_lead(
            db, workspace_id=user.workspace_id, lead_id=lead_id
        )
    except services.LeadNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    return [NoteOut.model_validate(r) for r in rows]


@router.post("", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
async def create_note(
    lead_id: UUID,
    payload: NoteCreate,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> NoteOut:
    try:
        row = await services.create(
            db,
            workspace_id=user.workspace_id,
            lead_id=lead_id,
            author=user,
            text=payload.text,
        )
    except services.LeadNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    await db.commit()
    return NoteOut.model_validate(row)


@router.patch("/{note_id}", response_model=NoteOut)
async def update_note(
    lead_id: UUID,
    note_id: UUID,
    payload: NoteUpdate,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> NoteOut:
    try:
        row = await services.update(
            db,
            workspace_id=user.workspace_id,
            lead_id=lead_id,
            note_id=note_id,
            actor=user,
            text=payload.text,
        )
    except services.NoteNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    except services.NoteForbidden:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the author or an admin can edit this note",
        )
    await db.commit()
    return NoteOut.model_validate(row)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    lead_id: UUID,
    note_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> None:
    try:
        await services.delete(
            db,
            workspace_id=user.workspace_id,
            lead_id=lead_id,
            note_id=note_id,
            actor=user,
        )
    except services.NoteNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    except services.NoteForbidden:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the author or an admin can delete this note",
        )
    await db.commit()
