"""Lead AI Agent REST endpoints — Sprint 3.1 Phase C.

Three endpoints, mounted at `/leads/{lead_id}/agent` (mirrors the
`/leads/{lead_id}/enrichment` shape introduced in Sprint 1.3):

  GET  /leads/{lead_id}/agent/suggestion           — read cached suggestion
  POST /leads/{lead_id}/agent/suggestion/refresh   — queue Celery refresh (202)
  POST /leads/{lead_id}/agent/chat                 — Sales Coach turn

Workspace isolation goes through `app.leads.repositories.get_by_id`,
which already enforces `workspace_id == current_user.workspace_id`.
A leaked lead UUID from another workspace returns 404 rather than
leaking data — the same pattern as `/leads/{id}/custom-attributes`.
"""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.auth.models import User
from app.db import get_db
from app.lead_agent.runner import chat as agent_chat
from app.lead_agent.schemas import (
    AgentSuggestion,
    ChatRequest,
    ChatResponse,
    SuggestionResponse,
)
from app.leads import repositories as leads_repo
from app.leads.models import Lead

router = APIRouter(prefix="/leads/{lead_id}/agent", tags=["lead-agent"])


async def _get_workspace_lead(
    db: AsyncSession, *, lead_id: UUID, workspace_id: UUID
) -> Lead:
    """Fetch a lead workspace-scoped or 404. Tiny resolver instead of
    a full FastAPI dependency — three endpoints share it, none need
    custom error mapping beyond 404."""
    lead = await leads_repo.get_by_id(db, lead_id, workspace_id)
    if lead is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )
    return lead


async def _resolve_stage_name(db: AsyncSession, lead: Lead) -> str | None:
    """Best-effort stage-name lookup for prompt context. Mirrors the
    helper in `app/lead_agent/tasks.py`; duplicated here so the
    request path doesn't depend on Celery-task imports."""
    if lead.stage_id is None:
        return None
    from app.pipelines.models import Stage

    res = await db.execute(select(Stage).where(Stage.id == lead.stage_id))
    stage = res.scalar_one_or_none()
    return stage.name if stage is not None else None


# ---------------------------------------------------------------------------
# GET /agent/suggestion — read cached banner content (no LLM call)
# ---------------------------------------------------------------------------

@router.get("/suggestion", response_model=SuggestionResponse)
async def get_lead_suggestion(
    lead_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> SuggestionResponse:
    """Return whatever `agent_state.suggestion` carries, or null when
    nothing has been computed yet. Cheap GET — never hits the LLM.
    The frontend banner is responsible for triggering a refresh on
    cold rows via the POST endpoint below."""
    lead = await _get_workspace_lead(
        db, lead_id=lead_id, workspace_id=user.workspace_id
    )

    state = lead.agent_state or {}
    raw = state.get("suggestion") if isinstance(state, dict) else None
    if not raw:
        return SuggestionResponse(suggestion=None)

    try:
        suggestion = AgentSuggestion(**raw)
    except Exception:
        # Stored row is malformed — treat as «no suggestion» so the
        # frontend doesn't crash. The next refresh overwrites it.
        return SuggestionResponse(suggestion=None)

    return SuggestionResponse(suggestion=suggestion)


# ---------------------------------------------------------------------------
# POST /agent/suggestion/refresh — queue background recomputation
# ---------------------------------------------------------------------------

@router.post(
    "/suggestion/refresh",
    status_code=status.HTTP_202_ACCEPTED,
)
async def refresh_lead_suggestion(
    lead_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> dict[str, str]:
    """Enqueue a Celery task to recompute the suggestion. Returns
    immediately with 202 — the frontend re-fetches via GET
    `/agent/suggestion` after a short poll (or eventually via WS).

    Lead existence is checked synchronously so a 404 surfaces here
    rather than silently failing inside the worker."""
    await _get_workspace_lead(
        db, lead_id=lead_id, workspace_id=user.workspace_id
    )

    # Lazy import — keeps the routers module from pulling Celery at
    # FastAPI startup if the worker process isn't running.
    from app.scheduled.jobs import lead_agent_refresh_suggestion

    lead_agent_refresh_suggestion.delay(str(lead_id))
    return {"status": "queued", "lead_id": str(lead_id)}


# ---------------------------------------------------------------------------
# POST /agent/chat — Sales Coach turn
# ---------------------------------------------------------------------------

@router.post("/chat", response_model=ChatResponse)
async def lead_chat(
    lead_id: UUID,
    payload: ChatRequest,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> ChatResponse:
    """One Sales Coach turn. Synchronous — the frontend awaits the
    LLM response. Uses MiMo Pro via `TaskType.sales_coach` per
    ADR-018; on LLM failure the runner returns a polite Russian
    fallback string and we still 200 the response."""
    lead = await _get_workspace_lead(
        db, lead_id=lead_id, workspace_id=user.workspace_id
    )
    stage_name = await _resolve_stage_name(db, lead)

    return await agent_chat(
        lead,
        message=payload.message,
        history=payload.history,
        stage_name=stage_name,
    )
