"""Admin REST for WebForms — Sprint 2.2 G1.

Public submit + embed.js endpoints land in Group 2 with their own
no-auth routing. This file is admin-only / authed-only.

Role gate: read endpoints accept any signed-in user in the workspace;
mutating endpoints (create / update / delete) require admin or head
role per `require_admin_or_head` (Sprint 1.5 pattern extended).

Path-conversion guard: admin endpoints take `{form_id: UUID}`. The
public submit/embed endpoints (Group 2) will use `{slug: str}` on a
DIFFERENT prefix so non-UUID values never reach this router's
parametric routes.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user, require_admin_or_head
from app.auth.models import User
from app.config import get_settings
from app.db import get_db
from app.forms import repositories as repo
from app.forms import services as svc
from app.forms.schemas import (
    FormAnalyticsOut,
    FormStatsOut,
    FormSubmissionOut,
    FormSubmissionPageOut,
    WebFormCreateIn,
    WebFormOut,
    WebFormPageOut,
    WebFormUpdateIn,
)

router = APIRouter(prefix="/api/forms", tags=["forms"])


def build_embed_snippet(slug: str) -> str:
    """`<script>` tag the manager copies into a landing page. Pulls
    `api_base_url` so the embed URL works across staging / prod /
    preview deployments without a frontend rebuild."""
    base = get_settings().api_base_url.rstrip("/")
    return f'<script src="{base}/api/forms/{slug}/embed.js" async></script>'


def serialize_form(form, *, include_token: bool = True) -> WebFormOut:
    out = WebFormOut.model_validate(form)
    out.embed_snippet = build_embed_snippet(form.slug)
    if not include_token:
        out.ingest_token = None
    return out


# ---------------------------------------------------------------------------
# Read — any authed user in the workspace
# ---------------------------------------------------------------------------

@router.get("", response_model=WebFormPageOut)
async def list_forms(
    is_active: Annotated[bool | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> WebFormPageOut:
    items, total = await repo.list_for_workspace(
        db,
        workspace_id=user.workspace_id,
        is_active=is_active,
        page=page,
        page_size=page_size,
    )
    is_privileged = user.role in ("admin", "head")
    return WebFormPageOut(
        items=[serialize_form(f, include_token=is_privileged) for f in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/analytics", response_model=FormAnalyticsOut)
async def get_analytics(
    date_from: Annotated[datetime | None, Query()] = None,
    date_to: Annotated[datetime | None, Query()] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> FormAnalyticsOut:
    return await svc.get_channel_analytics(
        db, workspace_id=user.workspace_id, date_from=date_from, date_to=date_to
    )


@router.get("/{form_id}", response_model=WebFormOut)
async def get_form(
    form_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> WebFormOut:
    try:
        form = await svc.get_form_or_404(
            db, form_id=form_id, workspace_id=user.workspace_id
        )
    except svc.WebFormNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    return serialize_form(form, include_token=user.role in ("admin", "head"))


@router.get("/{form_id}/submissions", response_model=FormSubmissionPageOut)
async def list_form_submissions(
    form_id: UUID,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> FormSubmissionPageOut:
    # Workspace guard — load the form first so we don't expose
    # cross-workspace submission counts via a known form_id.
    try:
        await svc.get_form_or_404(
            db, form_id=form_id, workspace_id=user.workspace_id
        )
    except svc.WebFormNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")

    items, total = await repo.list_submissions(
        db, form_id=form_id, page=page, page_size=page_size
    )
    return FormSubmissionPageOut(
        items=[FormSubmissionOut.model_validate(s) for s in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{form_id}/stats", response_model=FormStatsOut)
async def get_stats(
    form_id: UUID,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin_or_head)] = ...,
) -> FormStatsOut:
    """Per-form aggregates for the admin stats card."""
    # Workspace guard — mirrors the pattern in get_form and list_form_submissions:
    # verify the form belongs to the caller's workspace before serving stats.
    try:
        await svc.get_form_or_404(
            db, form_id=form_id, workspace_id=user.workspace_id
        )
    except svc.WebFormNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    response.headers["Cache-Control"] = "private, max-age=60"
    return await svc.get_form_stats(db, form_id=form_id)


# ---------------------------------------------------------------------------
# Mutate — admin / head only
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=WebFormOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_form(
    payload: WebFormCreateIn,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin_or_head)] = ...,
) -> WebFormOut:
    try:
        form = await svc.create_form(
            db,
            workspace_id=user.workspace_id,
            user_id=user.id,
            name=payload.name,
            fields_json=payload.fields_json,
            target_pipeline_id=payload.target_pipeline_id,
            target_stage_id=payload.target_stage_id,
            redirect_url=payload.redirect_url,
            default_assignee_id=payload.default_assignee_id,
            contact_task_sla_hours=payload.contact_task_sla_hours,
            source_label=payload.source_label,
            notify_email=payload.notify_email,
            require_key=payload.require_key,
        )
    except svc.WebFormInvalidTarget as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    await db.commit()
    await db.refresh(form)
    return serialize_form(form)


@router.patch("/{form_id}", response_model=WebFormOut)
async def update_form(
    form_id: UUID,
    payload: WebFormUpdateIn,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin_or_head)] = ...,
) -> WebFormOut:
    # Use exclude_unset so absent keys don't blow away existing values.
    patch = payload.model_dump(exclude_unset=True)
    try:
        form = await svc.update_form(
            db,
            form_id=form_id,
            workspace_id=user.workspace_id,
            patch=patch,
        )
    except svc.WebFormNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    except svc.WebFormInvalidTarget as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    await db.commit()
    await db.refresh(form)
    return serialize_form(form)


@router.delete("/{form_id}", response_model=WebFormOut)
async def delete_form(
    form_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin_or_head)] = ...,
) -> WebFormOut:
    """Soft delete — flips is_active=False, keeps the row + submissions
    so existing landing pages don't 404 silently. Public submit endpoint
    in Group 2 will check is_active before accepting new submissions."""
    try:
        form = await svc.delete_form(
            db, form_id=form_id, workspace_id=user.workspace_id
        )
    except svc.WebFormNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    await db.commit()
    await db.refresh(form)
    return serialize_form(form)


@router.post("/{form_id}/rotate-key", response_model=WebFormOut)
async def rotate_form_key(
    form_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin_or_head)] = ...,
) -> WebFormOut:
    try:
        form = await svc.rotate_key(db, form_id=form_id, workspace_id=user.workspace_id)
    except svc.WebFormNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    except svc.WebFormInvalidTarget as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(form)
    return serialize_form(form)


__all__ = ["router", "build_embed_snippet", "serialize_form"]
