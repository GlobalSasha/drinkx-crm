"""Lead-source dictionary REST endpoints — Sprint CEO G1.

  GET    /api/lead-sources            — list (all roles; ?active_only=true for the form)
  POST   /api/lead-sources            — create (admin / head)
  PATCH  /api/lead-sources/{id}       — rename / toggle active / paid (admin / head)
  DELETE /api/lead-sources/{id}       — delete; 409 on system rows (admin / head)
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.audit import log as log_audit_event
from app.auth.dependencies import current_user, require_admin_or_head
from app.auth.models import User
from app.db import get_db
from app.lead_sources import services as svc
from app.lead_sources.schemas import (
    LeadSourceCreateIn,
    LeadSourceOut,
    LeadSourceUpdateIn,
)

router = APIRouter(prefix="/lead-sources", tags=["lead-sources"])


@router.get("", response_model=list[LeadSourceOut])
async def list_lead_sources(
    active_only: Annotated[bool, Query()] = False,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> list[LeadSourceOut]:
    sources = await svc.list_sources(
        db, workspace_id=user.workspace_id, active_only=active_only
    )
    return sources  # type: ignore[return-value]


@router.post("", response_model=LeadSourceOut, status_code=status.HTTP_201_CREATED)
async def create_lead_source(
    payload: LeadSourceCreateIn,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin_or_head)] = ...,
) -> LeadSourceOut:
    try:
        source = await svc.create_source(
            db, workspace_id=user.workspace_id, payload=payload
        )
    except svc.LeadSourceNameConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="источник с таким названием уже есть",
        ) from exc
    await log_audit_event(
        db,
        workspace_id=user.workspace_id,
        user_id=user.id,
        action="lead_source.create",
        entity_type="lead_source",
        entity_id=source.id,
        delta={"name": source.name, "is_paid": source.is_paid},
    )
    await db.commit()
    return source  # type: ignore[return-value]


@router.patch("/{source_id}", response_model=LeadSourceOut)
async def update_lead_source(
    source_id: uuid.UUID,
    payload: LeadSourceUpdateIn,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin_or_head)] = ...,
) -> LeadSourceOut:
    try:
        source = await svc.update_source(
            db, source_id=source_id, workspace_id=user.workspace_id, payload=payload
        )
    except svc.LeadSourceNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="источник не найден"
        ) from exc
    except svc.LeadSourceNameConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="источник с таким названием уже есть",
        ) from exc
    await db.commit()
    return source  # type: ignore[return-value]


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lead_source(
    source_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin_or_head)] = ...,
) -> None:
    try:
        await svc.delete_source(
            db, source_id=source_id, workspace_id=user.workspace_id
        )
    except svc.LeadSourceNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="источник не найден"
        ) from exc
    except svc.LeadSourceIsSystem as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "lead_source_is_system",
                "message": "системный источник нельзя удалить — отключите его вместо удаления",
            },
        ) from exc
    await log_audit_event(
        db,
        workspace_id=user.workspace_id,
        user_id=user.id,
        action="lead_source.delete",
        entity_type="lead_source",
        entity_id=source_id,
        delta={},
    )
    await db.commit()
