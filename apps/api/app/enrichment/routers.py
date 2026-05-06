"""Enrichment REST endpoints."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.auth.models import User
from app.db import get_db, get_session_factory
from app.enrichment import services
from app.enrichment.api_schemas import EnrichmentRunOut, EnrichmentTriggerOut
from app.enrichment.orchestrator import run_enrichment
from app.leads.services import LeadNotFound

router = APIRouter(prefix="/leads/{lead_id}/enrichment", tags=["enrichment"])


async def _bg_run(run_id: UUID) -> None:
    """Background task: open a fresh DB session and run the orchestrator."""
    factory = get_session_factory()
    async with factory() as session:
        await run_enrichment(db=session, run_id=run_id)


@router.post("", response_model=EnrichmentTriggerOut, status_code=status.HTTP_202_ACCEPTED)
async def trigger(
    lead_id: UUID,
    background: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(current_user)],
) -> EnrichmentTriggerOut:
    """Trigger enrichment for a lead. Returns 202 immediately; runs in background."""
    try:
        run = await services.trigger_enrichment(
            db,
            workspace_id=user.workspace_id,
            user_id=user.id,
            lead_id=lead_id,
        )
    except LeadNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")

    await db.commit()
    background.add_task(_bg_run, run.id)
    return EnrichmentTriggerOut(enrichment_run_id=run.id, status=run.status)


@router.get("/latest", response_model=EnrichmentRunOut | None)
async def latest(
    lead_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(current_user)],
) -> EnrichmentRunOut | None:
    """Return the most recent enrichment run for this lead."""
    run = await services.get_latest_run(db, workspace_id=user.workspace_id, lead_id=lead_id)
    return run  # type: ignore[return-value]


@router.get("", response_model=list[EnrichmentRunOut])
async def list_runs(
    lead_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(current_user)],
    limit: int = Query(20, ge=1, le=100),
) -> list[EnrichmentRunOut]:
    """Return enrichment run history for this lead."""
    runs = await services.list_runs(db, workspace_id=user.workspace_id, lead_id=lead_id, limit=limit)
    return runs  # type: ignore[return-value]
