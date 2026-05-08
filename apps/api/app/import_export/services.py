"""Import-export service layer — Sprint 2.1 G1 skeleton.

Group 2 fills in upload / mapping / preview / apply. Here we ship just
enough to manage ImportJob lifecycle: create, list, get, cancel.
Confirm/apply uses the same pattern as Sprint 1.4 daily-plan regenerate
— REST creates the job, Celery worker fills it.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.import_export.mapper import apply_mapping
from app.import_export.models import (
    ExportJob,
    ExportJobFormat,
    ExportJobStatus,
    ImportJob,
    ImportJobStatus,
)
from app.import_export.validators import validate_row

log = structlog.get_logger()


class ImportJobNotFound(Exception):
    pass


class ImportJobBadState(Exception):
    """Raised when a transition isn't legal from the current status."""


class ExportJobNotFound(Exception):
    pass


class ExportJobBadFormat(Exception):
    pass


class ExportJobNotReady(Exception):
    """Download requested before the worker finished."""


class ExportPayloadGone(Exception):
    """Job is `done` but Redis lost the payload (TTL expired)."""


PREVIEW_ROWS = 100  # how many rows we surface in the preview UI


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

async def list_jobs(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[ImportJob], int]:
    page = max(page, 1)
    page_size = max(min(page_size, 100), 1)
    offset = (page - 1) * page_size

    base = select(ImportJob).where(ImportJob.workspace_id == workspace_id)
    if status:
        base = base.where(ImportJob.status == status)

    total_q = (
        select(func.count())
        .select_from(ImportJob)
        .where(ImportJob.workspace_id == workspace_id)
    )
    if status:
        total_q = total_q.where(ImportJob.status == status)
    total = int((await session.execute(total_q)).scalar_one() or 0)

    res = await session.execute(
        base.order_by(ImportJob.created_at.desc()).offset(offset).limit(page_size)
    )
    return list(res.scalars()), total


async def get_job(
    session: AsyncSession, *, job_id: UUID, workspace_id: UUID
) -> ImportJob:
    res = await session.execute(
        select(ImportJob)
        .where(ImportJob.id == job_id)
        .where(ImportJob.workspace_id == workspace_id)
    )
    job = res.scalar_one_or_none()
    if job is None:
        raise ImportJobNotFound(str(job_id))
    return job


# ---------------------------------------------------------------------------
# Mutations (Group 2 fills in the actual upload/parse/apply logic)
# ---------------------------------------------------------------------------

async def create_job(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    user_id: UUID,
    format: str,
    source_filename: str,
    upload_size_bytes: int,
    diff: dict[str, Any] | None = None,
) -> ImportJob:
    """Stage a new ImportJob with status='uploaded'. Group 2 calls this
    from the upload endpoint after parsing the file into the diff payload."""
    job = ImportJob(
        workspace_id=workspace_id,
        user_id=user_id,
        status=ImportJobStatus.uploaded.value,
        format=format,
        source_filename=source_filename[:300],
        upload_size_bytes=upload_size_bytes,
        diff_json=diff,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


async def confirm_mapping(
    session: AsyncSession,
    *,
    job_id: UUID,
    workspace_id: UUID,
    mapping: dict[str, str | None],
) -> ImportJob:
    """Persist the manager-confirmed column mapping, re-validate every row
    against the mapped shape, and roll the job to status='previewed'."""
    job = await get_job(session, job_id=job_id, workspace_id=workspace_id)
    if job.status != ImportJobStatus.uploaded.value:
        raise ImportJobBadState(
            f"confirm-mapping illegal in status={job.status}"
        )

    diff = dict(job.diff_json or {})
    all_rows = list(diff.get("all_rows") or [])

    mapped_rows = apply_mapping(all_rows, mapping)
    will_create = 0
    will_skip = 0
    errors_by_row: dict[str, list[str]] = {}
    for i, mr in enumerate(mapped_rows):
        errs = validate_row(mr)
        if errs:
            will_skip += 1
            errors_by_row[str(i)] = errs
        elif (mr.get("company_name") or "").strip():
            will_create += 1
        else:
            will_skip += 1

    diff["confirmed_mapping"] = mapping
    diff["mapped_rows"] = mapped_rows
    diff["dry_run_stats"] = {
        "will_create": will_create,
        "will_skip": will_skip,
        "errors": errors_by_row,
    }
    job.diff_json = diff
    job.status = ImportJobStatus.previewed.value
    await session.commit()
    await session.refresh(job)
    return job


async def request_apply(
    session: AsyncSession,
    *,
    job_id: UUID,
    workspace_id: UUID,
) -> ImportJob:
    """Flip the job into status='running' and dispatch the Celery task.
    The task itself owns the per-row create/error accounting."""
    job = await get_job(session, job_id=job_id, workspace_id=workspace_id)
    if job.status != ImportJobStatus.previewed.value:
        raise ImportJobBadState(
            f"apply illegal in status={job.status}"
        )
    job.status = ImportJobStatus.running.value
    await session.commit()
    await session.refresh(job)

    # Dispatch best-effort — Redis hiccup at request time should not
    # surface a 5xx if the row is already saved. The task is idempotent
    # via the status guard inside `_run_bulk_import`.
    try:
        from app.scheduled.celery_app import celery_app

        celery_app.send_task(
            "app.scheduled.jobs.bulk_import_run",
            args=[str(job.id)],
        )
    except Exception as exc:
        log.warning(
            "import.apply_dispatch_failed",
            job_id=str(job.id),
            error=str(exc)[:200],
        )
    return job


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

VALID_EXPORT_FORMATS = {fmt.value for fmt in ExportJobFormat}


async def create_export_job(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    user_id: UUID,
    format_value: str,
    filters: dict[str, Any] | None,
    include_ai_brief: bool,
) -> ExportJob:
    """Stage a fresh ExportJob with status='pending'. The Celery task
    `run_export_task` is dispatched separately by the router so the
    DB write commits before the worker can race the row read."""
    if format_value not in VALID_EXPORT_FORMATS:
        raise ExportJobBadFormat(f"unknown export format: {format_value}")

    payload_filters = dict(filters or {})
    # Carry include_ai_brief inside filters_json — keeps the schema
    # narrower; the worker pulls it back out at run time.
    payload_filters["include_ai_brief"] = bool(include_ai_brief)

    job = ExportJob(
        workspace_id=workspace_id,
        user_id=user_id,
        status=ExportJobStatus.pending.value,
        format=format_value,
        filters_json=payload_filters,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


async def get_export_job(
    session: AsyncSession, *, job_id: UUID, workspace_id: UUID
) -> ExportJob:
    res = await session.execute(
        select(ExportJob)
        .where(ExportJob.id == job_id)
        .where(ExportJob.workspace_id == workspace_id)
    )
    job = res.scalar_one_or_none()
    if job is None:
        raise ExportJobNotFound(str(job_id))
    return job


async def fetch_export_payload(
    session: AsyncSession,
    *,
    job_id: UUID,
    workspace_id: UUID,
) -> tuple[ExportJob, bytes]:
    """Resolve a download request. Raises:
      ExportJobNotFound — bad UUID or cross-workspace
      ExportJobNotReady — status != 'done'
      ExportPayloadGone — Redis miss (TTL expired)
    """
    from app.import_export.redis_bytes import fetch_export_bytes

    job = await get_export_job(session, job_id=job_id, workspace_id=workspace_id)
    if job.status != ExportJobStatus.done.value:
        raise ExportJobNotReady(job.status)
    if not job.redis_key:
        raise ExportPayloadGone("missing redis_key")
    data = await fetch_export_bytes(job.redis_key)
    if data is None:
        raise ExportPayloadGone("redis miss")
    return job, data


def export_job_out(job: ExportJob) -> dict[str, Any]:
    """ExportJobOut payload with the synthetic download_url."""
    return {
        "id": job.id,
        "workspace_id": job.workspace_id,
        "user_id": job.user_id,
        "status": job.status,
        "format": job.format,
        "row_count": job.row_count,
        "error": job.error,
        "created_at": job.created_at,
        "finished_at": job.finished_at,
        "download_url": (
            f"/api/export/{job.id}/download"
            if job.status == ExportJobStatus.done.value
            else None
        ),
    }


# ---------------------------------------------------------------------------
# Cancel (import-only — export tasks are short-running)
# ---------------------------------------------------------------------------

async def cancel_job(
    session: AsyncSession,
    *,
    job_id: UUID,
    workspace_id: UUID,
) -> ImportJob:
    """Allowed only while the job hasn't started running."""
    job = await get_job(session, job_id=job_id, workspace_id=workspace_id)
    if job.status in (
        ImportJobStatus.running.value,
        ImportJobStatus.succeeded.value,
        ImportJobStatus.failed.value,
        ImportJobStatus.cancelled.value,
    ):
        raise ImportJobBadState(
            f"cannot cancel job in status={job.status}"
        )
    job.status = ImportJobStatus.cancelled.value
    await session.commit()
    await session.refresh(job)
    return job
