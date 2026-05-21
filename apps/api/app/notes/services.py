"""LeadNote service layer — workspace-scoped, author/admin guarded."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.leads.services import LeadNotFound, get_lead
from app.notes.models import LeadNote

_DELETED_AUTHOR = "Удалённый пользователь"


class NoteNotFound(Exception):
    pass


class NoteForbidden(Exception):
    """Caller is neither the author nor an admin."""


def _to_dict(note: LeadNote, author_name: str | None) -> dict:
    return {
        "id": note.id,
        "lead_id": note.lead_id,
        "text": note.text,
        "created_at": note.created_at,
        "updated_at": note.updated_at,
        "author_id": note.user_id,
        "author_name": author_name or _DELETED_AUTHOR,
    }


async def list_for_lead(
    db: AsyncSession, *, workspace_id: uuid.UUID, lead_id: uuid.UUID
) -> list[dict]:
    await get_lead(db, workspace_id, lead_id)  # 404 if not in workspace
    rows = (
        await db.execute(
            select(LeadNote, User.name)
            .join(User, LeadNote.user_id == User.id, isouter=True)
            .where(
                LeadNote.workspace_id == workspace_id,
                LeadNote.lead_id == lead_id,
            )
            .order_by(LeadNote.created_at.desc())
        )
    ).all()
    return [_to_dict(note, name) for (note, name) in rows]


async def create(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
    author: User,
    text: str,
) -> dict:
    await get_lead(db, workspace_id, lead_id)
    note = LeadNote(
        workspace_id=workspace_id,
        lead_id=lead_id,
        user_id=author.id,
        text=text.strip(),
    )
    db.add(note)
    await db.flush()
    return _to_dict(note, author.name)


async def _get_owned_or_admin(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
    note_id: uuid.UUID,
    actor: User,
) -> LeadNote:
    note = (
        await db.execute(
            select(LeadNote).where(
                LeadNote.id == note_id,
                LeadNote.lead_id == lead_id,
                LeadNote.workspace_id == workspace_id,
            )
        )
    ).scalar_one_or_none()
    if note is None:
        raise NoteNotFound
    if note.user_id != actor.id and actor.role != "admin":
        raise NoteForbidden
    return note


async def update(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
    note_id: uuid.UUID,
    actor: User,
    text: str,
) -> dict:
    note = await _get_owned_or_admin(
        db, workspace_id=workspace_id, lead_id=lead_id, note_id=note_id, actor=actor
    )
    note.text = text.strip()
    await db.flush()
    # Resolve author name (the original author, not the editor).
    author_name = (
        await db.execute(select(User.name).where(User.id == note.user_id))
    ).scalar_one_or_none()
    return _to_dict(note, author_name)


async def delete(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    lead_id: uuid.UUID,
    note_id: uuid.UUID,
    actor: User,
) -> None:
    note = await _get_owned_or_admin(
        db, workspace_id=workspace_id, lead_id=lead_id, note_id=note_id, actor=actor
    )
    await db.delete(note)


__all__ = [
    "NoteNotFound",
    "NoteForbidden",
    "LeadNotFound",
    "list_for_lead",
    "create",
    "update",
    "delete",
]
