"""Import/export REST.

Sprint 2.1 G1: list / get / cancel.
Sprint 2.1 G2: upload + confirm-mapping + apply (this file).

Apply is async via Celery — the HTTP handler only flips status to
'running' and dispatches; the worker owns per-row accounting.
"""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.auth.models import User
from app.config import get_settings
from app.db import get_db
from app.import_export import services as svc
from app.import_export.field_map import LEAD_IMPORT_FIELDS
from app.import_export.mapper import apply_mapping, suggest_mapping
from app.import_export.models import ImportJobFormat, ImportJobStatus
from app.import_export.parsers import detect_format, parse_file
from app.import_export.schemas import ImportJobOut, ImportJobPageOut
from app.import_export.validators import validate_row

router = APIRouter(prefix="/api/import", tags=["import_export"])


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class ConfirmMappingIn(BaseModel):
    mapping: dict[str, str | None]


# ---------------------------------------------------------------------------
# G1: read + cancel
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# G2: upload + confirm-mapping + apply
# ---------------------------------------------------------------------------

@router.post("/upload", response_model=ImportJobOut)
async def upload(
    file: Annotated[UploadFile, File(...)],
    fmt: Annotated[str | None, Query(alias="format")] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> ImportJobOut:
    """Receive a file, parse it, suggest a column mapping, validate every
    row, persist a fresh ImportJob with status='uploaded'."""
    settings = get_settings()
    max_bytes = settings.import_max_upload_mb * 1024 * 1024

    content = await file.read()
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"file too large: > {settings.import_max_upload_mb}MB",
        )

    filename = file.filename or "upload"

    # Resolve format: explicit query param wins, otherwise sniff extension
    resolved: ImportJobFormat | None = None
    if fmt:
        try:
            resolved = ImportJobFormat(fmt)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"unknown format: {fmt}",
            )
    if resolved is None:
        resolved = detect_format(filename)
    if resolved is None or resolved in (
        ImportJobFormat.bitrix24,
        ImportJobFormat.amocrm,
        ImportJobFormat.bulk_update_yaml,
    ):
        # Adapter formats are wired in Groups 4/5/8.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="unsupported file extension; pass ?format=xlsx|csv|json|yaml",
        )

    parsed = parse_file(content, filename, resolved)
    if parsed.error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=parsed.error
        )

    suggestion = suggest_mapping(parsed.headers)

    # Validate against the suggested mapping so the preview surfaces
    # the validation summary the manager will see in step 2.
    sample_mapped = apply_mapping(parsed.rows, suggestion)
    errors_by_row: dict[str, list[str]] = {}
    for i, mapped in enumerate(sample_mapped):
        errs = validate_row(mapped)
        if errs:
            errors_by_row[str(i)] = errs

    diff = {
        "headers": parsed.headers,
        "suggested_mapping": suggestion,
        "rows": parsed.rows[:svc.PREVIEW_ROWS],
        "all_rows": parsed.rows,
        "validation_errors": errors_by_row,
        "field_catalog": [
            {
                "key": fdef.key,
                "label_ru": fdef.label_ru,
                "required": fdef.required,
            }
            for fdef in LEAD_IMPORT_FIELDS.values()
        ],
    }

    job = await svc.create_job(
        db,
        workspace_id=user.workspace_id,
        user_id=user.id,
        format=resolved.value,
        source_filename=filename,
        upload_size_bytes=len(content),
        diff=diff,
    )
    job.total_rows = parsed.row_count
    await db.commit()
    await db.refresh(job)
    return ImportJobOut.model_validate(job)


@router.post("/jobs/{job_id}/confirm-mapping", response_model=ImportJobOut)
async def confirm_mapping_endpoint(
    job_id: UUID,
    payload: ConfirmMappingIn,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> ImportJobOut:
    try:
        job = await svc.confirm_mapping(
            db,
            job_id=job_id,
            workspace_id=user.workspace_id,
            mapping=payload.mapping,
        )
    except svc.ImportJobNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    except svc.ImportJobBadState as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        )
    return ImportJobOut.model_validate(job)


@router.post(
    "/jobs/{job_id}/apply",
    response_model=ImportJobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def apply_job(
    job_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> ImportJobOut:
    try:
        job = await svc.request_apply(
            db, job_id=job_id, workspace_id=user.workspace_id
        )
    except svc.ImportJobNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    except svc.ImportJobBadState as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        )
    return ImportJobOut.model_validate(job)


__all__ = [
    "router",
    # Re-exported for direct in-process use (e.g. service tests):
    "ImportJobStatus",
]
