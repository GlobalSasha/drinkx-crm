"""Pipelines REST endpoints — Sprint 2.3 G1.

Surface:

  GET    /api/pipelines                     — list (all roles)
  POST   /api/pipelines                     — create (admin / head)
  PATCH  /api/pipelines/{id}                — rename / replace stages
                                              (admin / head)
  DELETE /api/pipelines/{id}                — delete with guards
                                              (admin / head)
  POST   /api/pipelines/{id}/set-default    — flip workspace default
                                              (admin / head)
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user, require_admin_or_head
from app.auth.models import User
from app.audit.audit import log as log_audit_event
from app.db import get_db
from app.pipelines import repositories as pipelines_repo
from app.pipelines import services as svc
from app.pipelines.schemas import (
    PipelineCreateIn,
    PipelineOut,
    PipelineUpdateIn,
)

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

@router.get("", response_model=list[PipelineOut])
async def list_pipelines(
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> list[PipelineOut]:
    pipelines = await svc.list_pipelines(db, workspace_id=user.workspace_id)
    return pipelines  # type: ignore[return-value]


@router.get("/{pipeline_id}", response_model=PipelineOut)
async def get_pipeline(
    pipeline_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> PipelineOut:
    try:
        pipeline = await svc.get_pipeline_or_404(
            db, pipeline_id=pipeline_id, workspace_id=user.workspace_id
        )
    except svc.PipelineNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="воронка не найдена"
        ) from exc
    return pipeline  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Write — admin / head only
# ---------------------------------------------------------------------------

@router.post(
    "",
    response_model=PipelineOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_pipeline_endpoint(
    payload: PipelineCreateIn,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin_or_head)] = ...,
) -> PipelineOut:
    pipeline = await svc.create_pipeline(
        db,
        workspace_id=user.workspace_id,
        name=payload.name,
        type_=payload.type,
        stages=[s.model_dump() for s in payload.stages],
    )
    await log_audit_event(
        db,
        workspace_id=user.workspace_id,
        user_id=user.id,
        action="pipeline.create",
        entity_type="pipeline",
        entity_id=pipeline.id,
        # Sprint 2.3 G4: stage_count is what the auditor actually wants
        # to know — was a giant or a tiny pipeline created. type is
        # already encoded in entity_type.
        delta={"name": pipeline.name, "stage_count": len(pipeline.stages)},
    )
    await db.commit()
    return pipeline  # type: ignore[return-value]


@router.patch("/{pipeline_id}", response_model=PipelineOut)
async def update_pipeline_endpoint(
    pipeline_id: uuid.UUID,
    payload: PipelineUpdateIn,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin_or_head)] = ...,
) -> PipelineOut:
    try:
        pipeline = await svc.update_pipeline(
            db,
            pipeline_id=pipeline_id,
            workspace_id=user.workspace_id,
            name=payload.name,
            type_=payload.type,
            stages=(
                [s.model_dump() for s in payload.stages]
                if payload.stages is not None
                else None
            ),
        )
    except svc.PipelineNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="воронка не найдена"
        ) from exc

    await db.commit()
    return pipeline  # type: ignore[return-value]


@router.delete("/{pipeline_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pipeline_endpoint(
    pipeline_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin_or_head)] = ...,
) -> None:
    # Capture name BEFORE the delete so the audit log can carry it
    # (the row will be gone by the time we emit). get-or-404 here is
    # the same lookup svc.delete_pipeline does internally — small
    # double-fetch we accept for the audit trail.
    try:
        pipeline = await svc.get_pipeline_or_404(
            db, pipeline_id=pipeline_id, workspace_id=user.workspace_id
        )
    except svc.PipelineNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="воронка не найдена"
        ) from exc
    pipeline_name = pipeline.name

    try:
        await svc.delete_pipeline(
            db, pipeline_id=pipeline_id, workspace_id=user.workspace_id
        )
    except svc.PipelineNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="воронка не найдена"
        ) from exc
    except svc.PipelineHasLeads as exc:
        # Carry the lead count in the structured detail so the UI can
        # render «Перенесите 47 лидов в другую воронку» without an
        # extra round-trip.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "pipeline_has_leads",
                "lead_count": exc.count,
                "message": (
                    f"в воронке {exc.count} лидов — перенесите их в другую "
                    "воронку перед удалением"
                ),
            },
        ) from exc
    except svc.PipelineIsDefault as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "pipeline_is_default",
                "message": (
                    "это воронка по умолчанию — назначьте другую перед "
                    "удалением"
                ),
            },
        ) from exc
    await log_audit_event(
        db,
        workspace_id=user.workspace_id,
        user_id=user.id,
        action="pipeline.delete",
        entity_type="pipeline",
        entity_id=pipeline_id,
        delta={"name": pipeline_name},
    )
    await db.commit()


@router.post("/{pipeline_id}/set-default", response_model=PipelineOut)
async def set_default_pipeline_endpoint(
    pipeline_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin_or_head)] = ...,
) -> PipelineOut:
    # Capture the previous default BEFORE the flip so the audit row
    # carries from_id → to_id (the actual delta). Otherwise we'd
    # only know what the workspace landed on, not what it left.
    from_id = await pipelines_repo.get_default_pipeline_id(
        db, workspace_id=user.workspace_id
    )

    try:
        pipeline = await svc.set_default_pipeline(
            db, pipeline_id=pipeline_id, workspace_id=user.workspace_id
        )
    except svc.PipelineNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="воронка не найдена"
        ) from exc

    await log_audit_event(
        db,
        workspace_id=user.workspace_id,
        user_id=user.id,
        action="pipeline.set_default",
        entity_type="pipeline",
        entity_id=pipeline.id,
        delta={
            "name": pipeline.name,
            "from_id": str(from_id) if from_id else None,
            "to_id": str(pipeline.id),
        },
    )
    await db.commit()
    return pipeline  # type: ignore[return-value]
