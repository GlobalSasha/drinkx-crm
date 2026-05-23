"""REST API for /api/base-update/* (admin/head only)."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin_or_head
from app.auth.models import User
from app.base_update import api_schemas as dto
from app.base_update import services as svc
from app.db import get_db

router = APIRouter(prefix="/api/base-update", tags=["base_update"])


@router.post("/jobs", response_model=dto.IngestJobOut, status_code=status.HTTP_202_ACCEPTED)
async def create_job(
    files: Annotated[list[UploadFile], File(...)],
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_or_head)],
) -> dto.IngestJobOut:
    raw_files: list[tuple[str, bytes]] = []
    for f in files:
        raw_files.append((f.filename or "", await f.read()))
    try:
        staged = svc._build_staged_files(raw_files)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    job = await svc.create_job(db, workspace_id=user.workspace_id, user_id=user.id, staged=staged)
    await db.commit()

    from app.scheduled.celery_app import celery_app
    celery_app.send_task("app.scheduled.jobs.base_update_extract", args=[str(job.id)])
    return dto.IngestJobOut.model_validate(job)


@router.get("/jobs", response_model=list[dto.IngestJobOut])
async def list_jobs(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_or_head)],
    limit: int = 20,
    offset: int = 0,
) -> list[dto.IngestJobOut]:
    rows = await svc.list_jobs(db, workspace_id=user.workspace_id, limit=limit, offset=offset)
    return [dto.IngestJobOut.model_validate(r) for r in rows]


@router.get("/jobs/{job_id}", response_model=dto.IngestJobOut)
async def get_job(
    job_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_or_head)],
) -> dto.IngestJobOut:
    try:
        job = await svc.get_job(db, workspace_id=user.workspace_id, job_id=job_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return dto.IngestJobOut.model_validate(job)


@router.get("/jobs/{job_id}/conflicts", response_model=list[dto.IngestConflictOut])
async def list_conflicts(
    job_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_or_head)],
    only_open: bool = True,
) -> list[dto.IngestConflictOut]:
    try:
        rows = await svc.list_conflicts(
            db, workspace_id=user.workspace_id, job_id=job_id, only_open=only_open
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return [dto.IngestConflictOut.model_validate(r) for r in rows]


@router.patch("/conflicts/{conflict_id}", response_model=dto.IngestConflictOut)
async def patch_conflict(
    conflict_id: uuid.UUID,
    body: dto.ResolveConflictIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_or_head)],
) -> dto.IngestConflictOut:
    try:
        cf = await svc.resolve_conflict(
            db,
            workspace_id=user.workspace_id,
            conflict_id=conflict_id,
            resolution=body.resolution,
            resolved_value=body.resolved_value,
            resolved_by=user.id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    await db.commit()
    return dto.IngestConflictOut.model_validate(cf)


@router.post(
    "/jobs/{job_id}/apply",
    response_model=dto.IngestJobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def apply(
    job_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_admin_or_head)],
) -> dto.IngestJobOut:
    try:
        job = await svc.mark_resolving(db, workspace_id=user.workspace_id, job_id=job_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await db.commit()

    from app.scheduled.celery_app import celery_app
    celery_app.send_task("app.scheduled.jobs.base_update_apply", args=[str(job.id)])
    return dto.IngestJobOut.model_validate(job)
