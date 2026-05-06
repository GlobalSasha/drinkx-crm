"""Pipelines REST endpoints."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.auth.models import User
from app.db import get_db
from app.pipelines import repositories as repo
from app.pipelines.schemas import PipelineOut

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


@router.get("", response_model=list[PipelineOut])
async def list_pipelines(
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> list[PipelineOut]:
    pipelines = await repo.list_for_workspace(db, user.workspace_id)
    return pipelines  # type: ignore[return-value]
