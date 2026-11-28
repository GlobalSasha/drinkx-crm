"""«Голос клиентов» endpoints.

The worker routes live under /worker, not /external: the /external surface is
read-only by design (tests/test_sec03_external_key_access.py). Same machine-key
mechanism, but a key here carries only the write:insights scope.

  GET  /worker/v1/insights/pending   — comments for the AI worker (key scope write:insights)
  POST /worker/v1/insights           — the worker's tags; checked and stored
  GET  /company/voice?period=week|month — the summary for the head's /today
  GET  /worker/v1/insights/digest-source — last 5 days of comments, by lead
  POST /worker/v1/insights/digest        — the worker's digest; checked and stored
  GET  /company/digest                   — «Сводка за 5 дней» for the head's /today
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin_or_head
from app.auth.models import User
from app.db import get_db
from app.external.dependencies import ServiceContext, require_service_key
from app.insights import digest as digest_svc
from app.insights import services as svc
from app.insights.categories import CATEGORIES
from app.insights.schemas import (
    CompanyDigestOut,
    CompanyVoiceOut,
    DigestIn,
    DigestInOut,
    DigestSourceOut,
    IngestIn,
    IngestOut,
    PendingOut,
)

SCOPE = "write:insights"

worker_router = APIRouter(prefix="/worker/v1/insights", tags=["insights"])
company_router = APIRouter(prefix="/company", tags=["company"])


@worker_router.get("/pending", response_model=PendingOut)
async def insights_pending(
    limit: int = Query(60, ge=1, le=200),
    ctx: Annotated[ServiceContext, Depends(require_service_key(SCOPE))] = ...,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
) -> PendingOut:
    comments = await svc.pending_comments(db, workspace_id=ctx.workspace_id, limit=limit)
    return PendingOut(
        categories=[{"key": k, "group": g, "label": lbl} for k, (g, lbl) in CATEGORIES.items()],
        comments=comments,
    )


@worker_router.post("", response_model=IngestOut)
async def insights_ingest(
    payload: IngestIn,
    ctx: Annotated[ServiceContext, Depends(require_service_key(SCOPE))] = ...,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
) -> IngestOut:
    result = await svc.ingest(db, workspace_id=ctx.workspace_id, payload=payload)
    await db.commit()
    return IngestOut(**result)


@company_router.get("/voice", response_model=CompanyVoiceOut)
async def company_voice(
    period: str = Query("week", pattern="^(week|month)$"),
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin_or_head)] = ...,
) -> CompanyVoiceOut:
    data = await svc.voice(db, workspace_id=user.workspace_id, period=period)
    return data  # type: ignore[return-value]


@worker_router.get("/digest-source", response_model=DigestSourceOut)
async def digest_source(
    ctx: Annotated[ServiceContext, Depends(require_service_key(SCOPE))] = ...,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
) -> DigestSourceOut:
    data = await digest_svc.digest_source(db, workspace_id=ctx.workspace_id)
    return data  # type: ignore[return-value]


@worker_router.post("/digest", response_model=DigestInOut)
async def digest_ingest(
    payload: DigestIn,
    ctx: Annotated[ServiceContext, Depends(require_service_key(SCOPE))] = ...,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
) -> DigestInOut:
    result = await digest_svc.store_digest(db, workspace_id=ctx.workspace_id, payload=payload)
    await db.commit()
    return DigestInOut(**result)


@company_router.get("/digest", response_model=CompanyDigestOut)
async def company_digest(
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin_or_head)] = ...,
) -> CompanyDigestOut:
    data = await digest_svc.company_digest(db, workspace_id=user.workspace_id)
    return data  # type: ignore[return-value]
