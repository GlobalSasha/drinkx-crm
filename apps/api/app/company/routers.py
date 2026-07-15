"""Company overview REST endpoints — Sprint CEO G4 (admin/head only).

  GET /api/company/summary?period=week|month   — incoming-lead pulse + sources + daily
  GET /api/company/attention                    — stuck leads + per-manager load
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin_or_head
from app.auth.models import User
from app.company import services as svc
from app.company.schemas import (
    CompanyAttentionOut,
    CompanyManagersOut,
    CompanySummaryOut,
)
from app.db import get_db

router = APIRouter(prefix="/company", tags=["company"])


@router.get("/summary", response_model=CompanySummaryOut)
async def company_summary(
    period: Annotated[str, Query()] = "week",
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin_or_head)] = ...,
) -> CompanySummaryOut:
    try:
        data = await svc.summary(db, workspace_id=user.workspace_id, period=period)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return data  # type: ignore[return-value]


@router.get("/attention", response_model=CompanyAttentionOut)
async def company_attention(
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin_or_head)] = ...,
) -> CompanyAttentionOut:
    data = await svc.attention(db, workspace_id=user.workspace_id)
    return data  # type: ignore[return-value]


@router.get("/managers", response_model=CompanyManagersOut)
async def company_managers(
    period: Annotated[str, Query()] = "week",
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin_or_head)] = ...,
) -> CompanyManagersOut:
    try:
        data = await svc.managers(db, workspace_id=user.workspace_id, period=period)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return data  # type: ignore[return-value]
