"""Admin LLM cost counter — read-only."""
from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin
from app.auth.models import User
from app.db import get_db
from app.llm_usage.schemas import LlmCostsOut
from app.llm_usage.service import get_costs

router = APIRouter(prefix="/admin/llm-costs", tags=["admin"])


@router.get("", response_model=LlmCostsOut)
async def llm_costs(
    period: Literal["this_month", "last_month", "all"] = "this_month",
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin)] = ...,
) -> LlmCostsOut:
    """Admin-only. Scoped to the caller's workspace (not user-supplied)."""
    return await get_costs(db, workspace_id=user.workspace_id, period=period)
