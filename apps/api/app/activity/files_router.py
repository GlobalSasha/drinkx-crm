"""REST endpoints for task file attachments."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.activity import files as svc
from app.activity.files import FileTooLarge, UnsupportedFileType, classify_upload
from app.activity.models import Activity, ActivityType
from app.activity.repositories import find_files_by_parent_task
from app.activity.services import _get_lead_or_raise
from app.auth.dependencies import current_user
from app.auth.models import User
from app.db import get_db
from app.leads.models import Lead

router = APIRouter(tags=["activity-files"])


class TaskFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    body: str | None = None
    file_kind: str | None = None
    file_name: str
    file_size: int
    parent_task_id: uuid.UUID | None = None
    created_at: datetime

    @classmethod
    def from_activity(cls, a: Activity) -> "TaskFileOut":
        pj = a.payload_json or {}
        parent_raw = pj.get("parent_task_id")
        try:
            parent = uuid.UUID(parent_raw) if parent_raw else None
        except (TypeError, ValueError):
            parent = None
        return cls(
            id=a.id, type=a.type, body=a.body, file_kind=a.file_kind,
            file_name=pj.get("file_name") or "unknown",
            file_size=int(pj.get("file_size") or 0),
            parent_task_id=parent,
            created_at=a.created_at,
        )


class DownloadOut(BaseModel):
    url: str
    expires_in: int


async def _get_file_activity_workspace_scoped(
    db: AsyncSession, *, activity_id: uuid.UUID, workspace_id: uuid.UUID
) -> Activity | None:
    """Fetch a file-Activity scoped to the workspace via its lead.
    Returns None if not found / wrong workspace / wrong type."""
    stmt = (
        select(Activity)
        .join(Lead, Lead.id == Activity.lead_id)
        .where(
            Activity.id == activity_id,
            Activity.type == ActivityType.file.value,
            Lead.workspace_id == workspace_id,
        )
    )
    return (await db.execute(stmt)).scalar_one_or_none()


@router.post(
    "/leads/{lead_id}/tasks/{task_id}/files",
    response_model=TaskFileOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload(
    lead_id: uuid.UUID,
    task_id: uuid.UUID,
    request: Request,
    file: Annotated[UploadFile, File(...)],
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(current_user)],
    caption: Annotated[str | None, Form()] = None,
) -> TaskFileOut:
    await _get_lead_or_raise(db, lead_id, user.workspace_id)

    # Cheap early-bail before Starlette buffers the multipart body to disk/memory.
    # Nginx caps externally at 25MB; this is defense-in-depth for internal callers.
    cl = request.headers.get("content-length")
    if cl:
        try:
            if int(cl) > svc.MAX_FILE_BYTES + 65536:  # 64KB slack for multipart envelope
                raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="file too large")
        except ValueError:
            pass  # malformed Content-Length — let the body read handle it

    # Bounded read (defends against header lying about size)
    raw = await file.read(svc.MAX_FILE_BYTES + 1)
    if len(raw) > svc.MAX_FILE_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="file too large")
    if not raw:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="empty file")

    try:
        kind, content_type = classify_upload(
            filename=file.filename or "",
            size=len(raw),
            content_head=raw[:64],
        )
    except UnsupportedFileType as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except FileTooLarge as exc:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)) from exc

    activity = await svc.upload_task_file(
        db,
        workspace_id=user.workspace_id,
        lead_id=lead_id,
        user_id=user.id,
        parent_task_id=task_id,
        filename=file.filename or "file",
        content=raw,
        content_type=content_type,
        kind=kind,
        caption=caption,
    )
    await db.commit()

    # Kick off content extraction (best-effort, runs in Celery).
    # Failure here must not break the upload response — the upload itself
    # is already persisted + the file is in storage.
    try:
        from app.scheduled.celery_app import celery_app
        celery_app.send_task(
            "app.scheduled.jobs.extract_task_file_content",
            args=[str(activity.id)],
        )
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).warning(
            "extraction.dispatch_failed",
            extra={"activity_id": str(activity.id), "error": str(exc)[:200]},
        )

    return TaskFileOut.from_activity(activity)


@router.get(
    "/leads/{lead_id}/tasks/{task_id}/files",
    response_model=list[TaskFileOut],
)
async def list_files(
    lead_id: uuid.UUID,
    task_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(current_user)],
    q: str | None = None,
) -> list[TaskFileOut]:
    await _get_lead_or_raise(db, lead_id, user.workspace_id)
    rows = await find_files_by_parent_task(
        db, lead_id=lead_id, task_id=task_id, q=q
    )
    return [TaskFileOut.from_activity(r) for r in rows]


@router.get(
    "/activities/{activity_id}/download",
    response_model=DownloadOut,
)
async def download(
    activity_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(current_user)],
) -> DownloadOut:
    activity = await _get_file_activity_workspace_scoped(
        db, activity_id=activity_id, workspace_id=user.workspace_id
    )
    if activity is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="file not found")
    url = await svc.signed_download_url(activity)
    return DownloadOut(url=url, expires_in=300)


@router.delete(
    "/activities/{activity_id}/file",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete(
    activity_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(current_user)],
) -> None:
    activity = await _get_file_activity_workspace_scoped(
        db, activity_id=activity_id, workspace_id=user.workspace_id
    )
    if activity is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="file not found")
    await svc.delete_file_activity(db, activity)
    await db.commit()
