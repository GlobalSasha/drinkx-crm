"""Enrichment REST endpoints."""
from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.auth.models import User
from app.db import get_db
from app.enrichment import services
from app.enrichment.api_schemas import EnrichmentRunOut, EnrichmentTriggerOut
from app.enrichment.orchestrator import run_enrichment
from app.enrichment.services import (
    EnrichmentAlreadyRunning,
    EnrichmentBudgetExceeded,
    EnrichmentConcurrencyLimit,
)
from app.leads.services import LeadNotFound

router = APIRouter(prefix="/leads/{lead_id}/enrichment", tags=["enrichment"])

EnrichmentMode = Literal["full", "append"]


async def _bg_run(run_id: UUID, mode: EnrichmentMode = "full") -> None:
    """Background task: open a per-task DB engine + session and run the
    orchestrator. NullPool mirrors the Sprint 1.4 pattern (see
    app/scheduled/jobs.py) — a long-running BG task shouldn't hold a
    connection from the shared request pool, which can starve concurrent
    requests or trip 'Future attached to a different loop' if the pooled
    connection was created against a different event loop's lifetime.

    Failure path (Sprint 2.7 G1): if the orchestrator raises before it
    can flip the row to 'succeeded' / 'failed' itself, this wrapper
    opens a fresh session, marks the row 'failed' with a truncated
    error, and reports to Sentry. Without this, a worker crash mid-run
    would strand `status='running'` forever.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.config import get_settings

    s = get_settings()
    engine = create_async_engine(
        s.database_url,
        echo=False,
        poolclass=NullPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        try:
            async with factory() as session:
                await run_enrichment(db=session, run_id=run_id, mode=mode)
        except Exception as exc:
            from app.common.sentry_capture import capture
            capture(
                exc,
                fingerprint=["enrichment-bg-run", "stranded"],
                tags={"site": "enrichment._bg_run"},
                extra={"run_id": str(run_id)},
            )
            await _mark_run_failed(factory, run_id, exc)
            raise
    finally:
        await engine.dispose()


async def _mark_run_failed(factory, run_id: UUID, exc: BaseException) -> None:
    """Best-effort flip of `EnrichmentRun.status` to 'failed' when the
    orchestrator raised before it could set its own terminal state.
    Soft no-op on any failure (we already reported the original cause)."""
    from sqlalchemy import select

    from app.enrichment.models import EnrichmentRun

    try:
        async with factory() as session:
            res = await session.execute(
                select(EnrichmentRun).where(EnrichmentRun.id == run_id)
            )
            row = res.scalar_one_or_none()
            if row is None or row.status in ("succeeded", "failed"):
                return
            row.status = "failed"
            row.error = f"{type(exc).__name__}: {exc}"[:1000]
            await session.commit()
    except Exception:  # pragma: no cover — defensive
        return


@router.post("", response_model=EnrichmentTriggerOut, status_code=status.HTTP_202_ACCEPTED)
async def trigger(
    lead_id: UUID,
    background: BackgroundTasks,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(current_user)],
    mode: EnrichmentMode = Query(
        "full",
        description="'full' overwrites lead.ai_data; 'append' merges only into empty keys.",
    ),
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
    except EnrichmentAlreadyRunning as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"detail": "enrichment already in progress", "run_id": str(e.run_id)},
        )
    except EnrichmentConcurrencyLimit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Слишком много одновременных enrichment в этом workspace",
        )
    except EnrichmentBudgetExceeded as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Дневной AI-бюджет исчерпан: ${e.spent:.2f} / ${e.cap:.2f}",
        )

    await db.commit()
    background.add_task(_bg_run, run.id, mode)
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
