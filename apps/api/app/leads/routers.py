"""Leads REST endpoints."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.auth.models import User
from app.automation.stage_change import StageTransitionBlocked, StageTransitionInvalid
from app.db import get_db
from app.leads import services
from app.leads.schemas import (
    GateViolationOut,
    LeadCreate,
    LeadListOut,
    LeadOut,
    LeadUpdate,
    MoveStageIn,
    SprintCreateIn,
    SprintCreateOut,
    TransferIn,
)
from app.leads.services import (
    LeadAlreadyClaimed,
    LeadNotFound,
    LeadNotOwnedByUser,
    StageNotFound,
    TransferTargetInvalid,
)

router = APIRouter(prefix="/leads", tags=["leads"])


@router.get("", response_model=LeadListOut)
async def list_leads(
    stage_id: UUID | None = None,
    segment: str | None = None,
    city: str | None = None,
    priority: str | None = None,
    deal_type: str | None = None,
    assigned_to: UUID | None = None,
    q: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> LeadListOut:
    filters = dict(
        stage_id=stage_id,
        segment=segment,
        city=city,
        priority=priority,
        deal_type=deal_type,
        assigned_to=assigned_to,
        q=q,
        page=page,
        page_size=page_size,
    )
    items, total = await services.list_leads(db, user.workspace_id, filters)
    return LeadListOut(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=LeadOut, status_code=status.HTTP_201_CREATED)
async def create_lead(
    payload: LeadCreate,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> LeadOut:
    lead = await services.create_lead(db, user.workspace_id, user.id, payload)
    await db.commit()
    return lead  # type: ignore[return-value]


@router.get("/pool", response_model=LeadListOut)
async def list_pool(
    city: str | None = None,
    segment: str | None = None,
    fit_min: float | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> LeadListOut:
    filters = dict(city=city, segment=segment, fit_min=fit_min, page=page, page_size=page_size)
    items, total = await services.list_pool(db, user.workspace_id, filters)
    return LeadListOut(items=items, total=total, page=page, page_size=page_size)


@router.post("/sprint", response_model=SprintCreateOut)
async def create_sprint(
    payload: SprintCreateIn,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> SprintCreateOut:
    items, requested = await services.claim_sprint(
        db,
        user.workspace_id,
        user.id,
        cities=payload.cities,
        segment=payload.segment,
        limit=payload.limit,
    )
    await db.commit()
    return SprintCreateOut(
        claimed_count=len(items),
        requested=requested,
        items=items,  # type: ignore[arg-type]
    )


@router.get("/{lead_id}", response_model=LeadOut)
async def get_lead(
    lead_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> LeadOut:
    from app.leads.repositories import get_by_id

    lead = await get_by_id(db, lead_id, user.workspace_id)
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    return lead  # type: ignore[return-value]


@router.patch("/{lead_id}", response_model=LeadOut)
async def update_lead(
    lead_id: UUID,
    payload: LeadUpdate,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> LeadOut:
    try:
        lead = await services.update_lead(db, user.workspace_id, lead_id, payload)
    except LeadNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    await db.commit()
    return lead  # type: ignore[return-value]


@router.delete("/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lead(
    lead_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> None:
    try:
        await services.delete_lead(db, user.workspace_id, lead_id)
    except LeadNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    await db.commit()


@router.post("/{lead_id}/claim", response_model=LeadOut)
async def claim_lead(
    lead_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> LeadOut:
    try:
        lead = await services.claim_lead(db, user.workspace_id, user.id, lead_id)
    except LeadAlreadyClaimed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Эту карточку только что взял другой менеджер",
        )
    await db.commit()
    return lead  # type: ignore[return-value]


@router.post("/{lead_id}/transfer", response_model=LeadOut)
async def transfer_lead(
    lead_id: UUID,
    payload: TransferIn,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> LeadOut:
    try:
        lead = await services.transfer_lead(
            db,
            user.workspace_id,
            user.id,
            user.role,
            lead_id,
            payload.to_user_id,
            payload.comment,
        )
    except LeadNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    except LeadNotOwnedByUser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not own this lead",
        )
    except TransferTargetInvalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Transfer target user not found in this workspace",
        )
    await db.commit()
    return lead  # type: ignore[return-value]


@router.post("/{lead_id}/move-stage", response_model=LeadOut)
async def move_stage(
    lead_id: UUID,
    payload: MoveStageIn,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> LeadOut:
    try:
        lead = await services.move_lead_stage(
            db,
            user.workspace_id,
            user.id,
            lead_id,
            payload.stage_id,
            gate_skipped=payload.gate_skipped,
            skip_reason=payload.skip_reason,
            lost_reason=payload.lost_reason,
        )
    except LeadNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    except StageNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stage not found")
    except StageTransitionInvalid as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except StageTransitionBlocked as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Stage transition blocked by gate criteria",
                "violations": [{"code": v.code, "message": v.message} for v in e.violations],
            },
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    await db.commit()
    return lead  # type: ignore[return-value]
