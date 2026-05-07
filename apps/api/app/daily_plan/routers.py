"""Daily plan REST endpoints."""
from __future__ import annotations

from datetime import date as DateType
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.auth.models import User
from app.daily_plan import services
from app.daily_plan.api_schemas import DailyPlanItemOut, DailyPlanOut, RegenerateOut
from app.db import get_db

router = APIRouter(tags=["daily-plan"])


@router.get("/me/today", response_model=DailyPlanOut | None)
async def get_my_today(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(current_user)],
) -> DailyPlanOut | None:
    plan = await services.get_today_plan_for_user(db, user=user)
    return plan  # type: ignore[return-value]


@router.get("/daily-plans/{plan_date}", response_model=DailyPlanOut | None)
async def get_plan_for_date(
    plan_date: DateType,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(current_user)],
) -> DailyPlanOut | None:
    plan = await services.get_plan_for_user_date(db, user_id=user.id, plan_date=plan_date)
    return plan  # type: ignore[return-value]


@router.post(
    "/daily-plans/{plan_date}/regenerate",
    response_model=RegenerateOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def regenerate(
    plan_date: DateType,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(current_user)],
) -> RegenerateOut:
    plan, task_id = await services.request_regenerate(db, user=user, plan_date=plan_date)
    return RegenerateOut(plan_id=plan.id, status=plan.status, task_id=task_id)


@router.post("/daily-plans/items/{item_id}/complete", response_model=DailyPlanItemOut)
async def complete_item(
    item_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(current_user)],
) -> DailyPlanItemOut:
    item = await services.mark_item_done(db, item_id=item_id, user_id=user.id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found or not owned",
        )
    await db.commit()
    return item  # type: ignore[return-value]
