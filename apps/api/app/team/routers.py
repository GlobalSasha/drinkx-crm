"""Team stats REST — Sprint 3.4 G1.

  GET /api/team/stats?period=today|week|month        — all managers
  GET /api/team/stats/{user_id}?period=...           — one manager + daily

Both gated to admin/head (managers can't snoop on their peers'
performance metrics).
"""
from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin_or_head
from app.auth.models import User
from app.db import get_db
from app.team import services as svc
from app.team.schemas import ManagerStatsOut, TeamStatsOut

router = APIRouter(prefix="/team", tags=["team"])

Period = Literal["today", "week", "month"]


@router.get("/stats", response_model=TeamStatsOut, response_model_by_alias=True)
async def get_team_stats(
    period: Period = Query("week"),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin_or_head)] = ...,
) -> TeamStatsOut:
    data = await svc.team_stats(
        db, workspace_id=user.workspace_id, period=period
    )
    return TeamStatsOut(**data)


@router.get(
    "/stats/{user_id}",
    response_model=ManagerStatsOut,
    response_model_by_alias=True,
)
async def get_manager_stats(
    user_id: uuid.UUID,
    period: Period = Query("week"),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin_or_head)] = ...,
) -> ManagerStatsOut:
    try:
        data = await svc.manager_stats(
            db, workspace_id=user.workspace_id,
            user_id=user_id, period=period,
        )
    except svc.UserNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="пользователь не найден",
        ) from exc
    return ManagerStatsOut(**data)
