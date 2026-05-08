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
from app.import_export.models import ImportJob, ImportJobStatus
from app.import_export.validators import validate_row

log = structlog.get_logger()


class ImportJobNotFound(Exception):
    pass


class ImportJobBadState(Exception):
    """Raised when a transition isn't legal from the current status."""


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
