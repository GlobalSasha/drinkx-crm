"""Followups REST endpoints — nested under /leads/{lead_id}/followups."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.auth.models import User
from app.db import get_db
from app.followups import services
from app.followups.schemas import FollowupCreate, FollowupOut, FollowupUpdate
from app.leads.services import LeadNotFound

router = APIRouter(prefix="/leads/{lead_id}/followups", tags=["followups"])


@router.get("", response_model=list[FollowupOut])
async def list_followups(
    lead_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> list[FollowupOut]:
    try:
        followups = await services.list_followups(db, user.workspace_id, lead_id)
    except LeadNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    return followups  # type: ignore[return-value]


@router.post("", response_model=FollowupOut, status_code=status.HTTP_201_CREATED)
async def create_followup(
    lead_id: UUID,
    payload: FollowupCreate,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> FollowupOut:
    try:
        fu = await services.create_followup(
            db, user.workspace_id, lead_id, payload.model_dump()
        )
    except LeadNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    await db.commit()
    return fu  # type: ignore[return-value]


@router.patch("/{fu_id}", response_model=FollowupOut)
async def update_followup(
    lead_id: UUID,
    fu_id: UUID,
    payload: FollowupUpdate,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> FollowupOut:
    try:
        fu = await services.update_followup(
            db, user.workspace_id, lead_id, fu_id,
            payload.model_dump(exclude_unset=True),
        )
    except LeadNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    except services.FollowupNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Followup not found")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    await db.commit()
    return fu  # type: ignore[return-value]


@router.delete("/{fu_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_followup(
    lead_id: UUID,
    fu_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> None:
    try:
        await services.delete_followup(db, user.workspace_id, lead_id, fu_id)
    except LeadNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    except services.FollowupNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Followup not found")
    await db.commit()


@router.post("/{fu_id}/complete", response_model=FollowupOut)
async def complete_followup(
    lead_id: UUID,
    fu_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> FollowupOut:
    try:
        fu = await services.complete_followup(db, user.workspace_id, lead_id, fu_id)
    except LeadNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    except services.FollowupNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Followup not found")
    await db.commit()
    return fu  # type: ignore[return-value]
