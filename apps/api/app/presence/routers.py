from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.auth.models import User
from app.db import get_db
from app.presence import repositories as repo
from app.presence.schemas import PingOut

router = APIRouter(prefix="/presence", tags=["presence"])


@router.post("/ping", response_model=PingOut)
async def presence_ping(
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> PingOut:
    await repo.record_ping(db, user_id=user.id, workspace_id=user.workspace_id)
    await db.commit()
    return PingOut(ok=True)
