"""Import/export REST — Sprint 2.1 G1 skeleton.

Group 1 ships read endpoints + cancel only. Group 2 will add upload +
mapping + preview, Group 6 will add export + status polling, Groups 8/9
will add the AI bulk-update flow.
"""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.auth.models import User
from app.db import get_db
from app.import_export import services as svc
from app.import_export.schemas import ImportJobOut, ImportJobPageOut

router = APIRouter(prefix="/api/import", tags=["import_export"])


@router.get("/jobs", response_model=ImportJobPageOut)
async def list_jobs(
    item_status: Annotated[str | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> ImportJobPageOut:
    items, total = await svc.list_jobs(
        db,
        workspace_id=user.workspace_id,
        status=item_status,
        page=page,
        page_size=page_size,
    )
    return ImportJobPageOut(
        items=[ImportJobOut.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/jobs/{job_id}", response_model=ImportJobOut)
async def get_job(
    job_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> ImportJobOut:
    try:
        job = await svc.get_job(db, job_id=job_id, workspace_id=user.workspace_id)
    except svc.ImportJobNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    return ImportJobOut.model_validate(job)


@router.post("/jobs/{job_id}/cancel", response_model=ImportJobOut)
async def cancel_job(
    job_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> ImportJobOut:
    try:
        job = await svc.cancel_job(
            db, job_id=job_id, workspace_id=user.workspace_id
        )
    except svc.ImportJobNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    except svc.ImportJobBadState as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        )
    return ImportJobOut.model_validate(job)
