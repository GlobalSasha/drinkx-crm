"""Orchestrator cores for base_update jobs.

These are awaited from the Celery task wrappers in app/scheduled/jobs.py.
Each core takes its own session (the Celery wrapper builds a NullPool
engine + session per task) and is best-effort per file/group — a single
extractor or apply failure does NOT abort the whole batch.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.base_update import constants as c
from app.base_update import services as svc
from app.base_update.dedup import dedup_batch
from app.base_update.extractor import extract_card
from app.base_update.models import IngestJob, IngestRecord
from app.base_update.schemas import ExtractedCard
from app.enrichment.budget import has_budget_remaining

log = logging.getLogger(__name__)


def _load_staged_files(job: IngestJob) -> list[dict]:
    stats = job.stats_json or {}
    files = stats.get("_staged_files") or []
    return [f for f in files if isinstance(f, dict) and f.get("filename") and f.get("text")]


def _clear_staged_files(job: IngestJob) -> None:
    stats = dict(job.stats_json or {})
    stats.pop("_staged_files", None)
    job.stats_json = stats or None


async def _get_job(db: AsyncSession, job_id: uuid.UUID) -> IngestJob | None:
    return (
        await db.execute(select(IngestJob).where(IngestJob.id == job_id))
    ).scalar_one_or_none()


async def _mark_job_failed(db: AsyncSession, job_id: uuid.UUID, exc: Exception) -> None:
    """Attempt to mark a job as JOB_FAILED in a clean transaction.

    Called from exception handlers where the original session may be poisoned —
    we rollback first then do a minimal update + commit."""
    try:
        await db.rollback()
        job = await _get_job(db, job_id)
        if job is not None:
            job.status = c.JOB_FAILED
            job.error = f"{type(exc).__name__}: {str(exc)[:300]}"
            await db.commit()
    except Exception:
        log.exception("base_update: failed to mark JOB_FAILED", extra={"job_id": str(job_id)})


async def run_extract_and_match(*, db: AsyncSession, job_id: uuid.UUID) -> None:
    """Phase 1+2+3: extract every staged .md via the LLM, dedup the batch,
    match against the base and auto-write the safe parts. Per-file failures
    become low-confidence conflicts; budget exhaustion stops further extracts
    and marks the job partial (status=ready, error=...)."""
    try:
        job = await _get_job(db, job_id)
        if job is None:
            log.error("base_update.run_extract_and_match: job not found", extra={"job_id": str(job_id)})
            return
        workspace_id = job.workspace_id

        job.status = c.JOB_EXTRACTING
        await db.commit()

        staged = _load_staged_files(job)

        extracted: list[tuple[ExtractedCard, list[str]]] = []
        budget_exhausted = False
        extract_failures: list[tuple[str, str]] = []  # (filename, error)

        for entry in staged:
            if not await has_budget_remaining(workspace_id):
                budget_exhausted = True
                break
            try:
                card = await extract_card(entry["text"], db=db, workspace_id=workspace_id)
                extracted.append((card, [entry["filename"]]))
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "base_update.extract_failed",
                    extra={"job_id": str(job_id), "filename": entry["filename"], "error": str(exc)[:200]},
                )
                # synthesise an empty card so the file shows up in the batch with a low-confidence flag
                extracted.append((ExtractedCard(), [entry["filename"]]))
                extract_failures.append((entry["filename"], str(exc)[:120]))

        job.status = c.JOB_MATCHING
        await db.commit()

        groups = dedup_batch(extracted)

        stats: dict = {
            "files": len(staged),
            "extracted": len(extracted),
            "groups": len(groups),
            "records_created": 0,
            "records_updated": 0,
            "records_conflict": 0,
            "conflicts_total": 0,
        }

        for grp in groups:
            record = IngestRecord(
                ingest_job_id=job.id,
                company_name=grp.primary.company.name or "",
                normalized_name=grp.normalized_name,
                extracted_json=grp.primary.model_dump(),
                source_files=list(grp.source_files),
            )
            db.add(record)
            try:
                await db.flush()  # need record.id for child conflicts
                action = await svc.apply_record(
                    db,
                    workspace_id=workspace_id,
                    record=record,
                    card=grp.primary,
                    source_files=list(grp.source_files),
                    dedup_conflict_field=grp.conflict_field if grp.conflict else None,
                )
                if action == c.ACTION_CREATED:
                    stats["records_created"] += 1
                elif action == c.ACTION_UPDATED:
                    stats["records_updated"] += 1
                elif action == c.ACTION_CONFLICT:
                    stats["records_conflict"] += 1
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "base_update.apply_record_failed",
                    extra={"job_id": str(job_id), "company": record.company_name, "error": str(exc)[:200]},
                )
                record.error = str(exc)[:300]
                record.action = c.ACTION_CONFLICT
                stats["records_conflict"] += 1

        # Count conflicts attached to this job's records
        from app.base_update.models import IngestConflict
        cnt = (
            await db.execute(
                select(IngestConflict).where(IngestConflict.ingest_job_id == job.id)
            )
        ).scalars().all()
        stats["conflicts_total"] = len(cnt)

        if extract_failures:
            stats["extract_failures"] = extract_failures

        if budget_exhausted:
            job.error = "llm_budget_exhausted"
        job.status = c.JOB_READY

    except Exception as exc:
        log.exception("base_update.extract_and_match failed", extra={"job_id": str(job_id)})
        await _mark_job_failed(db, job_id, exc)
        raise
    finally:
        # Always clear staged files so raw PII doesn't strand in stats_json on crash
        try:
            job_ref = await _get_job(db, job_id)
            if job_ref is not None:
                _clear_staged_files(job_ref)
                # Merge runtime stats if we have them
                if "stats" in dir():  # only if we got that far
                    merged = {**(job_ref.stats_json or {}), **stats}  # type: ignore[possibly-undefined]
                    job_ref.stats_json = merged
                await db.commit()
        except Exception:
            log.exception("base_update.extract_and_match: failed in finally cleanup")


async def run_apply_resolutions(*, db: AsyncSession, job_id: uuid.UUID) -> None:
    """Phase 2 of admin workflow: write every CONFLICT_RESOLVED decision and
    flip job.status to done (or back to ready if any remain open)."""
    try:
        job = await _get_job(db, job_id)
        if job is None:
            log.error("base_update.run_apply_resolutions: job not found", extra={"job_id": str(job_id)})
            return

        job.status = c.JOB_RESOLVING
        await db.commit()

        summary = await svc.apply_resolutions(db, workspace_id=job.workspace_id, job_id=job_id)

        # apply_resolutions sets job.status itself based on the open count; persist.
        log.info(
            "base_update.resolutions_applied",
            extra={"job_id": str(job_id), **summary},
        )
        await db.commit()

    except Exception as exc:
        log.exception("base_update.apply_resolutions failed", extra={"job_id": str(job_id)})
        await _mark_job_failed(db, job_id, exc)
        raise
