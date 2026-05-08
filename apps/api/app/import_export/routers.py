"""Import/export REST.

Sprint 2.1 G1: list / get / cancel.
Sprint 2.1 G2: upload + confirm-mapping + apply (this file).

Apply is async via Celery — the HTTP handler only flips status to
'running' and dispatches; the worker owns per-row accounting.
"""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.auth.models import User
from app.config import get_settings
from app.db import get_db
from app.import_export import services as svc
from app.import_export.adapters.bitrix24 import (
    apply_bitrix24_mapping,
    is_bitrix24,
    parse_bitrix24,
)
from app.import_export.bulk_update_prompt import BULK_UPDATE_PROMPT
from app.import_export.exporters import (
    content_type_for,
    file_extension_for,
)
from app.import_export.snapshot import generate_snapshot
from app.import_export.field_map import LEAD_IMPORT_FIELDS
from app.import_export.mapper import apply_mapping, suggest_mapping
from app.import_export.models import ImportJobFormat, ImportJobStatus
from app.import_export.parsers import detect_format, parse_file
from app.import_export.schemas import (
    ExportJobOut,
    ExportRequestIn,
    ImportJobOut,
    ImportJobPageOut,
)
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
        ImportJobFormat.amocrm,           # Group 5
        ImportJobFormat.bulk_update_yaml,  # Group 8
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="unsupported file extension; pass ?format=xlsx|csv|json|yaml|bitrix24",
        )

    if resolved == ImportJobFormat.bitrix24:
        parsed = parse_bitrix24(content)
    else:
        parsed = parse_file(content, filename, resolved)
    if parsed.error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=parsed.error
        )

    # Auto-detect: a CSV with Bitrix24-native headers gets the explicit
    # treatment without `?format=bitrix24`. Manager just drops the file in.
    auto_bitrix = (
        resolved == ImportJobFormat.csv and is_bitrix24(parsed.headers)
    )
    if resolved == ImportJobFormat.bitrix24 or auto_bitrix:
        suggestion = apply_bitrix24_mapping(parsed.headers)
        if auto_bitrix:
            # Reflect the actual treatment in the audit row, not the wire format.
            resolved = ImportJobFormat.bitrix24
    else:
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


# ---------------------------------------------------------------------------
# G6: export — Celery + Redis-backed download
# ---------------------------------------------------------------------------

export_router = APIRouter(prefix="/api/export", tags=["import_export"])


@export_router.post(
    "",
    response_model=ExportJobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_export(
    payload: ExportRequestIn,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> ExportJobOut:
    """Create an ExportJob and dispatch the Celery task. Returns 202
    with the job row — clients poll GET /api/export/{id} for status."""
    try:
        job = await svc.create_export_job(
            db,
            workspace_id=user.workspace_id,
            user_id=user.id,
            format_value=payload.format,
            filters=payload.filters,
            include_ai_brief=payload.include_ai_brief,
        )
    except svc.ExportJobBadFormat as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )

    # Dispatch best-effort. Redis hiccup at request time should not 5xx —
    # `_run_export` is idempotent via the status guard.
    try:
        from app.scheduled.celery_app import celery_app

        celery_app.send_task(
            "app.scheduled.jobs.run_export",
            args=[str(job.id)],
        )
    except Exception:  # noqa: BLE001 — defensive
        pass

    return ExportJobOut.model_validate(svc.export_job_out(job))


# ---- AI bulk-update loop (PRD §6.14, Sprint 2.1 G8) ----------------
# Static paths registered BEFORE /{job_id} so FastAPI's matcher hits
# them on `GET /api/export/snapshot` etc. — otherwise the parametric
# UUID converter would intercept and reject "snapshot" / "bulk-update-prompt".

@export_router.get("/snapshot")
async def get_snapshot(
    include_ai_brief: Annotated[bool, Query()] = True,
    stage_id: Annotated[UUID | None, Query()] = None,
    segment: Annotated[str | None, Query()] = None,
    city: Annotated[str | None, Query()] = None,
    priority: Annotated[str | None, Query()] = None,
    deal_type: Annotated[str | None, Query()] = None,
    assigned_to: Annotated[UUID | None, Query()] = None,
    assignment_status: Annotated[str | None, Query()] = None,
    fit_min: Annotated[float | None, Query()] = None,
    q: Annotated[str | None, Query()] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> StreamingResponse:
    """Synchronous YAML snapshot for the AI bulk-update flow.

    Capped at 500 leads per call — bigger workspaces should split via
    filters, the external LLM context window can't take more anyway.
    """
    filters = {
        k: v
        for k, v in {
            "stage_id": stage_id,
            "segment": segment,
            "city": city,
            "priority": priority,
            "deal_type": deal_type,
            "assigned_to": assigned_to,
            "assignment_status": assignment_status,
            "fit_min": fit_min,
            "q": q,
        }.items()
        if v is not None
    }

    payload = await generate_snapshot(
        db,
        workspace_id=user.workspace_id,
        filters=filters,
        include_ai_brief=include_ai_brief,
    )

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename = f"leads_snapshot_{date_str}.yaml"

    def _gen():
        yield payload

    return StreamingResponse(
        _gen(),
        media_type="application/yaml",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(payload)),
        },
    )


@export_router.get("/bulk-update-prompt")
async def get_bulk_update_prompt(
    user: Annotated[User, Depends(current_user)] = ...,
) -> dict[str, str]:
    """Return the canonical prompt the manager pastes into Claude /
    ChatGPT alongside `leads_snapshot.yaml`. Server-side constant so we
    can revise the format without a frontend deploy."""
    return {"prompt": BULK_UPDATE_PROMPT}


@export_router.get("/{job_id}", response_model=ExportJobOut)
async def get_export(
    job_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> ExportJobOut:
    try:
        job = await svc.get_export_job(
            db, job_id=job_id, workspace_id=user.workspace_id
        )
    except svc.ExportJobNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    return ExportJobOut.model_validate(svc.export_job_out(job))


@export_router.get("/{job_id}/download")
async def download_export(
    job_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> StreamingResponse:
    try:
        job, data = await svc.fetch_export_payload(
            db, job_id=job_id, workspace_id=user.workspace_id
        )
    except svc.ExportJobNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    except svc.ExportJobNotReady:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Файл ещё не готов",
        )
    except svc.ExportPayloadGone:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Файл устарел, создайте новый экспорт",
        )

    ext = file_extension_for(job.format)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename = f"leads_{date_str}.{ext}"

    def _gen():
        yield data

    return StreamingResponse(
        _gen(),
        media_type=content_type_for(job.format),
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(data)),
        },
    )


__all__ = [
    "router",
    "export_router",
    # Re-exported for direct in-process use (e.g. service tests):
    "ImportJobStatus",
]
