"""Pipelines service layer — Sprint 2.3 G1.

The router is intentionally thin; everything that needs to be
defensible — workspace scoping, the «can't delete with leads on it»
guard, the «can't delete the workspace default» guard — lives here so
the same shape can be exercised from the upcoming Settings UI without
re-implementing the rules client-side.
"""
from __future__ import annotations

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.pipelines import repositories as repo
from app.pipelines.models import Pipeline

log = structlog.get_logger()


# ---------------------------------------------------------------------------
# Custom exceptions — router maps to the right HTTP status
# ---------------------------------------------------------------------------

class PipelineNotFound(Exception):
    """404 — pipeline doesn't exist or isn't in the caller's workspace."""


class PipelineHasLeads(Exception):
    """409 — refuse to delete a pipeline with leads on it. Carries
    the count so the UI can render «Перенесите N лидов в другую воронку»
    without an extra API round-trip."""

    def __init__(self, count: int) -> None:
        super().__init__(f"pipeline has {count} leads on it")
        self.count = count


class PipelineIsDefault(Exception):
    """409 — refuse to delete the workspace's current default pipeline.
    Forces the admin to set a new default first; otherwise the
    workspace would be left with `default_pipeline_id=NULL` and the
    next sign-in would have nothing to land on."""


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

async def list_pipelines(
    session: AsyncSession, *, workspace_id: uuid.UUID
) -> list[Pipeline]:
    return await repo.list_for_workspace(session, workspace_id=workspace_id)


async def get_pipeline_or_404(
    session: AsyncSession,
    *,
    pipeline_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> Pipeline:
    pipeline = await repo.get_by_id(
        session, pipeline_id=pipeline_id, workspace_id=workspace_id
    )
    if pipeline is None:
        raise PipelineNotFound(str(pipeline_id))
    return pipeline


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

async def create_pipeline(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    name: str,
    type_: str = "sales",
    stages: list[dict],
) -> Pipeline:
    """Create a new pipeline + its initial stages. Caller commits.

    The `stages` payload is whatever the caller provides — we don't
    silently inject DEFAULT_STAGES because the multi-pipeline use-case
    is precisely «my partners funnel has different stages from sales».
    Empty stage lists are rejected at the schema layer (min_length=1).
    """
    return await repo.create_pipeline(
        session,
        workspace_id=workspace_id,
        name=name,
        type_=type_,
        stages=stages,
    )


async def update_pipeline(
    session: AsyncSession,
    *,
    pipeline_id: uuid.UUID,
    workspace_id: uuid.UUID,
    name: str | None = None,
    type_: str | None = None,
    stages: list[dict] | None = None,
) -> Pipeline:
    """Rename + optionally replace the stage list. Caller commits.

    Stage replacement is full — the editor sends the entire list back
    on save. `leads.stage_id` is FK SET NULL so deleted stages don't
    cascade-delete the leads, but a stale lead lands at stage=null
    until the manager reassigns. The Settings UI surfaces this
    explicitly («N лидов потеряют стадию»)."""
    pipeline = await get_pipeline_or_404(
        session, pipeline_id=pipeline_id, workspace_id=workspace_id
    )
    if name is not None or type_ is not None:
        pipeline = await repo.rename_pipeline(
            session, pipeline=pipeline, name=name, type_=type_
        )
    if stages is not None:
        pipeline = await repo.replace_stages(
            session, pipeline=pipeline, stages=stages
        )
    return pipeline


async def delete_pipeline(
    session: AsyncSession,
    *,
    pipeline_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> None:
    """Defensive delete — refuses if leads are on it OR if it's the
    current workspace default. Caller commits."""
    pipeline = await get_pipeline_or_404(
        session, pipeline_id=pipeline_id, workspace_id=workspace_id
    )

    # Guard 1: workspace default. Read through the canonical FK so a
    # workspace whose `default_pipeline_id` was hand-edited (via a
    # data fix) is still respected.
    current_default = await repo.get_default_pipeline_id(
        session, workspace_id=workspace_id
    )
    if current_default == pipeline.id:
        raise PipelineIsDefault()

    # Guard 2: leads on it.
    lead_count = await repo.count_leads_on_pipeline(
        session, pipeline_id=pipeline.id
    )
    if lead_count > 0:
        raise PipelineHasLeads(count=lead_count)

    await repo.hard_delete_pipeline(session, pipeline=pipeline)


async def set_default_pipeline(
    session: AsyncSession,
    *,
    pipeline_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> Pipeline:
    """Flip the workspace's default to the given pipeline. Validates
    workspace ownership via get-or-404 so a cross-workspace POST
    returns 404 not silent success. Caller commits.

    Sprint 2.3 G4: fans out a system-kind notification to every
    admin + head in the workspace so they see «Основная воронка
    изменена» on their next bell drawer poll. Wrapped in try/except
    — a notification storm or a User-table hiccup must never unwind
    the actual default-flip; safe_notify is also defensive on its
    own, the outer guard covers the User query."""
    pipeline = await get_pipeline_or_404(
        session, pipeline_id=pipeline_id, workspace_id=workspace_id
    )
    await repo.set_default(
        session, workspace_id=workspace_id, pipeline_id=pipeline.id
    )
    log.info(
        "pipelines.default_set",
        workspace_id=str(workspace_id),
        pipeline_id=str(pipeline.id),
    )

    await _notify_default_change(
        session,
        workspace_id=workspace_id,
        pipeline_name=pipeline.name,
    )

    return pipeline


async def _notify_default_change(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    pipeline_name: str,
) -> None:
    """Best-effort fan-out: stage one Notification row per admin/head
    in the workspace. Plain managers are NOT notified — the default
    change matters at the configuration level, not the day-to-day
    pipeline view (their /pipeline switcher already reflects the new
    default on next ['me'] refetch).

    Defensive against any failure in the User lookup or notify call —
    the parent set_default_pipeline must succeed regardless."""
    try:
        from sqlalchemy import select

        from app.auth.models import User
        from app.notifications.services import safe_notify

        result = await session.execute(
            select(User.id).where(
                User.workspace_id == workspace_id,
                User.role.in_(["admin", "head"]),
            )
        )
        for (admin_id,) in result.all():
            await safe_notify(
                session,
                workspace_id=workspace_id,
                user_id=admin_id,
                kind="system",
                title="Основная воронка изменена",
                body=f"Новая основная воронка: «{pipeline_name}»",
            )
    except Exception as exc:  # noqa: BLE001 — never block default-flip
        log.warning(
            "pipelines.default_notify_failed",
            workspace_id=str(workspace_id),
            error=str(exc)[:200],
        )
