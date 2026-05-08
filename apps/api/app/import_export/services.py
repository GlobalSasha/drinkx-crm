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

from app.import_export.models import ImportJob, ImportJobStatus

log = structlog.get_logger()


class ImportJobNotFound(Exception):
    pass


class ImportJobBadState(Exception):
    """Raised when a transition isn't legal from the current status."""


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
