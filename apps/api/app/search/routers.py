"""Global search endpoint — `GET /api/search?q=…&limit=20`."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.auth.models import User
from app.db import get_db
from app.search import repositories as search_repo
from app.search.schemas import SearchHit, SearchResponse

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=SearchResponse)
async def search(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(current_user)],
    q: str = Query("", description="Query text. 1-2 chars → ILIKE only; 3+ → trigram."),
    limit: int = Query(20, ge=1, le=50),
) -> SearchResponse:
    # Менеджер ищет только по своим лидам: с 2026-09-14 он не видит чужие
    # карточки нигде, включая глобальный поиск. Руководитель и админ — по всем.
    rows, mode = await search_repo.search(
        db,
        workspace_id=user.workspace_id,
        q=q,
        limit=limit,
        owner_id=None if user.role in ("admin", "head") else user.id,
    )
    items = [
        SearchHit(
            type=r["type"],
            id=r["id"],
            title=r["title"] or "",
            subtitle=r["subtitle"] or None,
            lead_id=r["lead_id"],
            url=r["url"],
            rank=r["rank"],
        )
        for r in rows
    ]
    return SearchResponse(items=items, total=len(items), query=q.strip(), mode=mode)  # type: ignore[arg-type]
