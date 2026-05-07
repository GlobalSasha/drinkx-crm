"""Audit log REST — admin-only read endpoint."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import repositories as repo
from app.audit.schemas import AuditLogOut, AuditLogPageOut
from app.auth.dependencies import require_admin
from app.auth.models import User
from app.db import get_db

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=AuditLogPageOut)
async def list_audit(
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin)] = ...,
) -> AuditLogPageOut:
    """Admin-only. Always scoped to caller's workspace — `workspace_id` is
    not user-supplied, it comes from the authenticated User row."""
    items, total = await repo.list_for_workspace(
        db,
        workspace_id=user.workspace_id,
        entity_type=entity_type,
        entity_id=entity_id,
        page=page,
        page_size=page_size,
    )
    return AuditLogPageOut(
        items=[AuditLogOut.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
    )
