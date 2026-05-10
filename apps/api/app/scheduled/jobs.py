"""Cron tasks. Each task wraps an async core in a fresh DB session.

Pattern:
- @celery_app.task signature is sync (Celery requirement)
- It opens a DB session via get_session_factory()
- It calls an async core function with that session
- A ScheduledJob audit row is written on every invocation with affected_count + error
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from uuid import UUID, uuid4

import structlog

from app.db import get_session_factory  # noqa: F401  # kept for tests that monkeypatch this symbol
from app.scheduled.celery_app import celery_app

log = structlog.get_logger()


@celery_app.task(name="app.scheduled.jobs.daily_plan_generator")
def daily_plan_generator() -> dict:
    """Hourly: process workspaces where the local clock just hit 08:00."""
    from app.scheduled.daily_plan_runner import run_daily_plan_for_all_users
    return asyncio.run(_run("daily_plan_generator", run_daily_plan_for_all_users))


@celery_app.task(name="app.scheduled.jobs.followup_reminder_dispatcher")
def followup_reminder_dispatcher() -> dict:
    """Every 15 min: create Activity reminders for followups due within 24h."""
    from app.followups.dispatcher import run_followup_dispatch
    return asyncio.run(_run("followup_reminder_dispatcher", run_followup_dispatch))


@celery_app.task(name="app.scheduled.jobs.daily_email_digest")
def daily_email_digest() -> dict:
    """Hourly at :30 — emails the digest to users whose local clock is 08."""
    from app.scheduled.digest_runner import run_daily_digest_for_all_users
    return asyncio.run(_run("daily_email_digest", run_daily_digest_for_all_users))


@celery_app.task(name="app.scheduled.jobs.regenerate_for_user")
def regenerate_for_user(user_id: str, plan_date_iso: str) -> dict:
    """Manual trigger from the UI. Generates one user's plan, ignoring the
    08:00-local-time gate the hourly cron uses."""
    return asyncio.run(_run_one_user_regen(UUID(user_id), date.fromisoformat(plan_date_iso)))


@celery_app.task(name="app.scheduled.jobs.gmail_history_sync")
def gmail_history_sync(user_id: str) -> dict:
    """One-time backfill dispatched from /api/inbox/gmail/callback.

    Pulls the last GMAIL_HISTORY_MONTHS of mail for the given user and
    seeds the incremental cursor.
    """
    return asyncio.run(_run_gmail_history_sync(UUID(user_id)))


@celery_app.task(name="app.scheduled.jobs.gmail_incremental_sync")
def gmail_incremental_sync() -> dict:
    """Every 5 min: process new messages for every active gmail channel."""
    from app.inbox.sync import incremental_sync_for_all
    return asyncio.run(_run("gmail_incremental_sync", incremental_sync_for_all))


@celery_app.task(name="app.scheduled.jobs.generate_inbox_suggestion")
def generate_inbox_suggestion(inbox_item_id: str) -> dict:
    """AI prefilter for an unmatched InboxItem — proposes create_lead /
    add_contact / match_lead. Failures are silent (suggested_action stays NULL)."""
    return asyncio.run(_run_inbox_suggestion(UUID(inbox_item_id)))


@celery_app.task(name="app.scheduled.jobs.run_export")
def run_export(job_id: str) -> dict:
    """Bulk-export task — render the requested format to bytes,
    stash in Redis with a 1h TTL, mark the ExportJob as `done`."""
    return asyncio.run(_run_export(UUID(job_id)))


@celery_app.task(name="app.scheduled.jobs.run_bulk_update")
def run_bulk_update(job_id: str) -> dict:
    """AI bulk-update apply (PRD §6.14, Sprint 2.1 G9). Walks
    `diff_json.items`, runs each through `apply_diff_item`, writes
    one ImportError per failure, updates progress counters."""
    return asyncio.run(_run_bulk_update(UUID(job_id)))


@celery_app.task(name="app.scheduled.jobs.bulk_import_run")
def bulk_import_run(job_id: str) -> dict:
    """Sprint 2.1 G1 skeleton — Group 2 fills in the parse/apply body.

    Loads the ImportJob row, walks its `diff_json`, applies confirmed rows
    against Lead / Contact / Activity, updates progress counters, writes
    one ImportError row per failure. Per-task NullPool engine like the
    other Celery tasks (Sprint 1.4 pattern).
    """
    return asyncio.run(_run_bulk_import(UUID(job_id)))


@celery_app.task(name="app.scheduled.jobs.automation_step_scheduler")
def automation_step_scheduler() -> dict:
    """Sprint 2.7 G2 — every 5 min, fire any due multi-step automation
    step rows. Step 0 already fired synchronously inside the original
    trigger fan-out; this task drives steps 1+ where `executed_at IS
    NULL AND scheduled_at <= now()`."""
    from app.automation_builder.services import execute_due_step_runs

    async def _core(session) -> int:
        result = await execute_due_step_runs(session)
        # `affected_count` on the ScheduledJob audit row needs an int.
        # Use the count that was actually scanned this tick.
        return int(result.get("scanned", 0) or 0)

    return asyncio.run(_run("automation_step_scheduler", _core))


@celery_app.task(name="app.scheduled.jobs.lead_agent_refresh_suggestion")
def lead_agent_refresh_suggestion(lead_id: str) -> dict:
    """Sprint 3.1 Phase C — recompute the lead-agent suggestion for one
    lead. Triggered manually from `POST /leads/{id}/agent/suggestion/refresh`
    (3.1+ may also fire it from automation hooks). The async core lives
    in `app.lead_agent.tasks` to keep domain code self-contained; this
    wrapper is the standard sync entry-point Celery requires."""
    from app.lead_agent.tasks import refresh_suggestion_async

    return asyncio.run(refresh_suggestion_async(UUID(lead_id)))


@celery_app.task(name="app.scheduled.jobs.lead_agent_scan_silence")
def lead_agent_scan_silence() -> dict:
    """Sprint 3.1 Phase C — beat task. Every 6 hours scan active leads
    where `last_activity_at` is older than the silence threshold and
    queue `lead_agent_refresh_suggestion` for each one so the actual
    LLM work runs in the worker pool (not the beat process)."""
    from app.lead_agent.tasks import scan_silence_async

    return asyncio.run(scan_silence_async())


def _build_task_engine_and_factory():
    """Each Celery task needs its own engine because asyncio.run() creates a
    fresh event loop per invocation, while asyncpg connections are bound to
    the loop they were created on. Re-using a global engine across loops
    raises 'Future attached to a different loop'. NullPool is right for
    short-lived cron work — connections are created and closed per task.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.config import get_settings

    s = get_settings()
    engine = create_async_engine(
        s.database_url,
        echo=False,
        poolclass=NullPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, factory


_INBOX_SUGGESTION_SYSTEM = """Ты — sales-аналитик DrinkX (умные кофе-станции для розницы и HoReCa).
Получаешь кратко: email отправителя и тему письма. Решаешь — это потенциальный
B2B клиент DrinkX (сети кофеен, HoReCa, ритейл, заправки, foodmarkets) или нет.
Если да — предложи действие.

Возвращай РОВНО один JSON-объект, первый символ `{`, без markdown.
Схема:
{
  "action": "create_lead" | "add_contact" | "match_lead" | "ignore",
  "company_name": str,    // что распознал; пусто если ignore
  "contact_name": str,    // если есть в имени отправителя; иначе пусто
  "confidence": number    // 0.0..1.0
}"""


_INBOX_SUGGESTION_USER = """Email отправителя: {from_email}
Тема: {subject}
Превью: {body_preview}

Это потенциальный клиент DrinkX? Верни JSON по схеме."""


async def _run_inbox_suggestion(inbox_item_id: UUID) -> dict:
    """Best-effort AI prefilter for an unmatched email.

    Never raises — on any failure leaves InboxItem.suggested_action=None.
    """
    import json as _json
    from sqlalchemy import select
    from app.inbox.models import InboxItem
    from app.enrichment.providers.base import LLMError, TaskType
    from app.enrichment.providers.factory import complete_with_fallback

    engine, factory = _build_task_engine_and_factory()
    try:
        async with factory() as session:
            res = await session.execute(
                select(InboxItem).where(InboxItem.id == inbox_item_id)
            )
            item = res.scalar_one_or_none()
            if item is None:
                return {"job": "generate_inbox_suggestion", "error": "not_found"}

            user_prompt = _INBOX_SUGGESTION_USER.format(
                from_email=item.from_email or "",
                subject=item.subject or "",
                body_preview=(item.body_preview or "")[:500],
            )
            try:
                completion = await complete_with_fallback(
                    system=_INBOX_SUGGESTION_SYSTEM,
                    user=user_prompt,
                    task_type=TaskType.prefilter,
                    max_tokens=300,
                    temperature=0.2,
                )
            except LLMError as e:
                log.warning(
                    "inbox.suggestion.llm_failed",
                    inbox_item_id=str(inbox_item_id),
                    error=str(e)[:200],
                )
                return {"job": "generate_inbox_suggestion", "error": "llm_failed"}

            text = (completion.text or "").strip()
            if text.startswith("```"):
                lines = text.splitlines()
                text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
            try:
                parsed = _json.loads(text)
            except (ValueError, _json.JSONDecodeError):
                log.warning(
                    "inbox.suggestion.parse_failed",
                    inbox_item_id=str(inbox_item_id),
                    raw_preview=text[:200],
                )
                return {"job": "generate_inbox_suggestion", "error": "parse_failed"}

            if not isinstance(parsed, dict) or "action" not in parsed:
                return {"job": "generate_inbox_suggestion", "error": "bad_shape"}

            cleaned = {
                "action": str(parsed.get("action", "ignore")),
                "company_name": str(parsed.get("company_name") or "")[:200],
                "contact_name": str(parsed.get("contact_name") or "")[:200],
                "confidence": float(parsed.get("confidence") or 0.0),
                "lead_id": None,
            }
            item.suggested_action = cleaned
            await session.commit()
            return {"job": "generate_inbox_suggestion", "action": cleaned["action"]}
    except Exception as exc:
        log.exception(
            "inbox.suggestion.task_failed",
            inbox_item_id=str(inbox_item_id),
            error=str(exc)[:200],
        )
        return {"job": "generate_inbox_suggestion", "error": str(exc)[:200]}
    finally:
        await engine.dispose()


async def _run_bulk_update(job_id: UUID) -> dict:
    """Per-item apply for the AI bulk-update format. Mirrors the
    bulk_import_run shape — per-row commit so the UI poll sees real-
    time progress, per-item rollback on exception, ImportError row
    per failure."""
    from datetime import datetime, timezone as _tz
    from sqlalchemy import select

    from app.import_export.diff_engine import (
        apply_diff_item,
        diff_from_jsonable,
    )
    from app.import_export.models import (
        ImportError,
        ImportJob,
        ImportJobStatus,
    )

    engine, factory = _build_task_engine_and_factory()
    try:
        async with factory() as session:
            res = await session.execute(
                select(ImportJob).where(ImportJob.id == job_id)
            )
            job = res.scalar_one_or_none()
            if job is None:
                return {"job": "run_bulk_update", "error": "not_found"}

            if job.status not in (
                ImportJobStatus.running.value,
                ImportJobStatus.previewed.value,
            ):
                log.info(
                    "bulk_update.skipped_due_to_status",
                    job_id=str(job_id),
                    status=job.status,
                )
                return {"job": "run_bulk_update", "skipped": job.status}

            if job.status != ImportJobStatus.running.value:
                job.status = ImportJobStatus.running.value
                await session.commit()

            diff = job.diff_json or {}
            items = diff_from_jsonable(diff.get("items") or [])
            workspace_id = job.workspace_id
            user_id = job.user_id

            for idx, item in enumerate(items):
                try:
                    if item.error:
                        # Resolution-time error — count as failed but
                        # don't try to apply.
                        session.add(ImportError(
                            job_id=job.id,
                            row_number=idx,
                            field="match",
                            message=item.error[:1000],
                        ))
                        job.failed += 1
                    else:
                        ok = await apply_diff_item(
                            session,
                            item=item,
                            workspace_id=workspace_id,
                            user_id=user_id,
                        )
                        if ok:
                            job.succeeded += 1
                        else:
                            session.add(ImportError(
                                job_id=job.id,
                                row_number=idx,
                                field="apply",
                                message=(
                                    "apply_diff_item returned False — "
                                    "see worker logs for details"
                                ),
                            ))
                            job.failed += 1
                except Exception as exc:
                    await session.rollback()
                    session.add(ImportError(
                        job_id=job.id,
                        row_number=idx,
                        field="",
                        message=f"{type(exc).__name__}: {exc}"[:1000],
                    ))
                    job.failed += 1
                finally:
                    job.processed += 1
                    await session.commit()

            job.status = (
                ImportJobStatus.succeeded.value
                if job.failed == 0
                else ImportJobStatus.failed.value
            )
            if job.failed:
                job.error_summary = (
                    f"{job.failed}/{job.total_rows} apply failures — "
                    "см. import_errors"
                )
            job.finished_at = datetime.now(tz=_tz.utc)
            await session.commit()
            return {
                "job": "run_bulk_update",
                "id": str(job_id),
                "succeeded": job.succeeded,
                "failed": job.failed,
            }
    except Exception as exc:
        log.exception("run_bulk_update.failed", job_id=str(job_id))
        return {"job": "run_bulk_update", "error": f"{type(exc).__name__}: {exc}"}
    finally:
        await engine.dispose()


async def _run_export(job_id: UUID) -> dict:
    """Fetch leads with the saved filter snapshot, encode in the requested
    format, store bytes in Redis, mark the row done.

    Per-task NullPool engine (Sprint 1.4 pattern). Failures land in
    ExportJob.error with status='failed' so the polling client can
    surface a useful message.
    """
    from datetime import datetime, timezone as _tz
    from sqlalchemy import select

    from app.auth.models import User
    from app.import_export.exporters import (
        export_csv,
        export_json,
        export_md_zip,
        export_xlsx,
        export_yaml,
        leads_to_rows,
    )
    from app.import_export.models import (
        ExportJob,
        ExportJobFormat,
        ExportJobStatus,
    )
    from app.import_export.redis_bytes import store_export_bytes
    from app.leads.models import Lead
    from app.pipelines.models import Stage

    engine, factory = _build_task_engine_and_factory()
    try:
        async with factory() as session:
            res = await session.execute(
                select(ExportJob).where(ExportJob.id == job_id)
            )
            job = res.scalar_one_or_none()
            if job is None:
                return {"job": "run_export", "error": "not_found"}

            if job.status not in (
                ExportJobStatus.pending.value,
                ExportJobStatus.running.value,
            ):
                return {"job": "run_export", "skipped": job.status}

            job.status = ExportJobStatus.running.value
            await session.commit()

            try:
                filters = dict(job.filters_json or {})
                include_ai_brief = bool(filters.pop("include_ai_brief", False))

                # Build the lead query from saved filters. We mirror the
                # filter set GET /api/leads accepts but DON'T limit by
                # assignment_status — exporting "everything in workspace"
                # is the common case and the manager can narrow via filters.
                stmt = select(Lead).where(Lead.workspace_id == job.workspace_id)
                if filters.get("stage_id"):
                    stmt = stmt.where(Lead.stage_id == filters["stage_id"])
                if filters.get("segment"):
                    stmt = stmt.where(Lead.segment == filters["segment"])
                if filters.get("city"):
                    stmt = stmt.where(Lead.city == filters["city"])
                if filters.get("priority"):
                    stmt = stmt.where(Lead.priority == filters["priority"])
                if filters.get("deal_type"):
                    stmt = stmt.where(Lead.deal_type == filters["deal_type"])
                if filters.get("assigned_to"):
                    stmt = stmt.where(Lead.assigned_to == filters["assigned_to"])
                if filters.get("assignment_status"):
                    stmt = stmt.where(
                        Lead.assignment_status == filters["assignment_status"]
                    )
                if filters.get("fit_min") is not None:
                    try:
                        stmt = stmt.where(
                            Lead.fit_score >= float(filters["fit_min"])
                        )
                    except (TypeError, ValueError):
                        pass
                if filters.get("q"):
                    stmt = stmt.where(
                        Lead.company_name.ilike(f"%{filters['q']}%")
                    )
                stmt = stmt.order_by(Lead.created_at.desc())

                leads_res = await session.execute(stmt)
                leads = list(leads_res.scalars())

                # Resolve relations the exporters need without N+1
                stage_ids = {l.stage_id for l in leads if l.stage_id}
                user_ids = {l.assigned_to for l in leads if l.assigned_to}
                stage_lookup: dict = {}
                user_email_lookup: dict = {}
                if stage_ids:
                    s_res = await session.execute(
                        select(Stage.id, Stage.name).where(Stage.id.in_(stage_ids))
                    )
                    stage_lookup = {sid: name for sid, name in s_res.all()}
                if user_ids:
                    u_res = await session.execute(
                        select(User.id, User.email).where(User.id.in_(user_ids))
                    )
                    user_email_lookup = {uid: email for uid, email in u_res.all()}

                fmt = job.format
                if fmt == ExportJobFormat.md_zip.value:
                    payload = export_md_zip(
                        leads,
                        stage_lookup=stage_lookup,
                        user_email_lookup=user_email_lookup,
                    )
                else:
                    rows = leads_to_rows(
                        leads,
                        stage_lookup=stage_lookup,
                        user_email_lookup=user_email_lookup,
                        include_ai_brief=include_ai_brief,
                    )
                    if fmt == ExportJobFormat.csv.value:
                        payload = export_csv(rows)
                    elif fmt == ExportJobFormat.json.value:
                        payload = export_json(rows)
                    elif fmt == ExportJobFormat.yaml.value:
                        payload = export_yaml(rows)
                    elif fmt == ExportJobFormat.xlsx.value:
                        payload = export_xlsx(rows)
                    else:
                        raise ValueError(f"unsupported format: {fmt}")

                redis_key = await store_export_bytes(str(job_id), payload)
                job.redis_key = redis_key
                job.row_count = len(leads)
                job.status = ExportJobStatus.done.value
                job.finished_at = datetime.now(tz=_tz.utc)
                await session.commit()
                return {
                    "job": "run_export",
                    "id": str(job_id),
                    "rows": len(leads),
                    "bytes": len(payload),
                }
            except Exception as exc:
                log.exception("run_export.failed", job_id=str(job_id))
                job.status = ExportJobStatus.failed.value
                job.error = f"{type(exc).__name__}: {exc}"[:1000]
                job.finished_at = datetime.now(tz=_tz.utc)
                await session.commit()
                return {
                    "job": "run_export",
                    "error": f"{type(exc).__name__}: {exc}",
                }
    finally:
        await engine.dispose()


async def _run_bulk_import(job_id: UUID) -> dict:
    """Apply a previewed ImportJob: create one Lead per mapped row, write
    one ImportError per failed row, update the job's progress counters in
    one commit per row so the UI poll can show real-time progress.

    The HTTP `/apply` handler already flipped the job to status='running'
    before dispatch — we double-check here so a manual replay (`celery -A
    app.scheduled.celery_app call ...`) on a `previewed` job still works.

    ADR-007: only fields that the manager confirmed via the mapping
    surface on the new lead. Extras (deal_amount, notes) land on a
    single Activity(type='comment') so we don't drop user data.
    """
    from datetime import datetime, timezone as _tz
    from sqlalchemy import select

    from app.activity.models import Activity
    from app.import_export.field_map import (
        DIRECT_LEAD_COLUMNS,
        EXTRAS_FOR_COMMENT,
        TAG_FIELD,
    )
    from app.import_export.models import ImportError, ImportJob, ImportJobStatus
    from app.import_export.validators import parse_deal_amount
    from app.leads.models import Lead
    from app.pipelines import repositories as pipelines_repo

    engine, factory = _build_task_engine_and_factory()
    try:
        async with factory() as session:
            res = await session.execute(
                select(ImportJob).where(ImportJob.id == job_id)
            )
            job = res.scalar_one_or_none()
            if job is None:
                return {"job": "bulk_import_run", "error": "not_found"}

            if job.status not in (
                ImportJobStatus.running.value,
                ImportJobStatus.previewed.value,
            ):
                log.info(
                    "bulk_import.skipped_due_to_status",
                    job_id=str(job_id),
                    status=job.status,
                )
                return {"job": "bulk_import_run", "skipped": job.status}

            # Idempotent transition — `/apply` already does this, but the
            # task can be invoked directly (or after a worker crash).
            if job.status != ImportJobStatus.running.value:
                job.status = ImportJobStatus.running.value
                await session.commit()

            mapped_rows = list(((job.diff_json or {}).get("mapped_rows")) or [])
            workspace_id = job.workspace_id
            user_id = job.user_id

            # Resolve default-pipeline first stage once per job — same
            # placement rule as the inbox 'create_lead' flow.
            first = await pipelines_repo.get_default_first_stage(
                session, workspace_id
            )
            pipeline_id, stage_id = first if first is not None else (None, None)

            for i, row in enumerate(mapped_rows):
                try:
                    company = (row.get("company_name") or "").strip()
                    if not company:
                        # confirmed_mapping shouldn't have let an empty
                        # company_name through, but defend anyway.
                        session.add(
                            ImportError(
                                job_id=job.id,
                                row_number=i,
                                field="company_name",
                                message="empty company_name — row skipped",
                            )
                        )
                        job.failed += 1
                        continue

                    tags_raw = row.get(TAG_FIELD) or ""
                    tags = [
                        t.strip() for t in tags_raw.split(",") if t.strip()
                    ] if tags_raw else []

                    lead_kwargs: dict[str, object] = {
                        "workspace_id": workspace_id,
                        "pipeline_id": pipeline_id,
                        "stage_id": stage_id,
                        "company_name": company[:255],
                        "assignment_status": "pool",
                        "tags_json": tags,
                        "source": (row.get("source") or "import")[:60],
                    }
                    for col in DIRECT_LEAD_COLUMNS:
                        if col == "company_name" or col == "source":
                            continue  # already set above
                        v = row.get(col)
                        if v:
                            lead_kwargs[col] = v
                    if "priority" in lead_kwargs:
                        # Validators already gated values to A/B/C/D
                        lead_kwargs["priority"] = str(
                            lead_kwargs["priority"]
                        ).upper()

                    lead = Lead(**lead_kwargs)
                    session.add(lead)
                    await session.flush()  # need lead.id

                    # Stash extras into a comment so we don't lose data.
                    extras = {k: row.get(k) for k in EXTRAS_FOR_COMMENT if row.get(k)}
                    if extras:
                        amt = extras.get("deal_amount")
                        amt_parsed = parse_deal_amount(amt) if amt else None
                        comment_lines = ["Импортировано:"]
                        if amt_parsed is not None:
                            comment_lines.append(f"Сумма сделки: {amt_parsed}")
                        elif amt:
                            comment_lines.append(f"Сумма сделки: {amt}")
                        if extras.get("notes"):
                            comment_lines.append(f"Заметки: {extras['notes']}")
                        session.add(
                            Activity(
                                lead_id=lead.id,
                                user_id=user_id,
                                type="comment",
                                payload_json={
                                    "text": "\n".join(comment_lines),
                                    "source": "import",
                                    "import_job_id": str(job.id),
                                },
                            )
                        )

                    job.succeeded += 1
                except Exception as exc:
                    # Roll back this row only, don't poison subsequent rows.
                    await session.rollback()
                    session.add(
                        ImportError(
                            job_id=job.id,
                            row_number=i,
                            field="",
                            message=f"{type(exc).__name__}: {exc}"[:1000],
                        )
                    )
                    job.failed += 1
                finally:
                    job.processed += 1
                    await session.commit()

            job.status = (
                ImportJobStatus.succeeded.value
                if job.failed == 0
                else ImportJobStatus.failed.value
            )
            if job.failed:
                job.error_summary = (
                    f"{job.failed}/{job.total_rows} rows failed — "
                    "see import_errors for details"
                )
            job.finished_at = datetime.now(tz=_tz.utc)
            await session.commit()
            return {
                "job": "bulk_import_run",
                "id": str(job_id),
                "succeeded": job.succeeded,
                "failed": job.failed,
            }
    except Exception as exc:
        log.exception("bulk_import_run.failed", job_id=str(job_id))
        return {"job": "bulk_import_run", "error": f"{type(exc).__name__}: {exc}"}
    finally:
        await engine.dispose()


async def _run_gmail_history_sync(user_id: UUID) -> dict:
    """Per-task NullPool engine + audit row for the one-shot backfill."""
    from app.daily_plan.models import ScheduledJob
    from app.inbox.sync import history_sync_for_user

    engine, factory = _build_task_engine_and_factory()
    started = datetime.now(timezone.utc)
    affected = 0
    error: str | None = None
    try:
        async with factory() as session:
            audit = ScheduledJob(
                id=uuid4(),
                job_name="gmail_history_sync",
                started_at=started,
                status="running",
            )
            session.add(audit)
            await session.commit()

            try:
                affected = await history_sync_for_user(session, user_id=user_id)
                audit.status = "succeeded"
            except Exception as e:
                error = f"{type(e).__name__}: {e}"
                audit.status = "failed"
                audit.error = error[:2000]
                log.exception("gmail_history_sync.failed", user_id=str(user_id))
            finally:
                audit.affected_count = affected
                audit.finished_at = datetime.now(timezone.utc)
                await session.commit()
    finally:
        await engine.dispose()

    return {
        "job": "gmail_history_sync",
        "user_id": str(user_id),
        "affected": affected,
        "error": error,
    }


async def _run_one_user_regen(user_id: UUID, plan_date: date) -> dict:
    engine, factory = _build_task_engine_and_factory()
    try:
        async with factory() as session:
            from sqlalchemy import select

            from app.auth.models import User
            from app.daily_plan.services import generate_for_user

            res = await session.execute(select(User).where(User.id == user_id))
            user = res.scalar_one_or_none()
            if user is None:
                return {"job": "regenerate_for_user", "error": "user_not_found"}
            try:
                plan = await generate_for_user(session, user=user, plan_date=plan_date)
                return {"job": "regenerate_for_user", "plan_id": str(plan.id), "status": plan.status}
            except Exception as e:
                log.exception("regenerate_for_user.failed", user_id=str(user_id))
                return {"job": "regenerate_for_user", "error": f"{type(e).__name__}: {e}"}
    finally:
        await engine.dispose()


async def _run(job_name: str, async_core) -> dict:
    """Common audit + execution wrapper. Builds a fresh engine+session
    factory per task — see _build_task_engine_and_factory for why."""
    from app.daily_plan.models import ScheduledJob

    engine, factory = _build_task_engine_and_factory()
    started = datetime.now(timezone.utc)
    affected = 0
    error: str | None = None

    try:
        async with factory() as session:
            audit = ScheduledJob(
                id=uuid4(),
                job_name=job_name,
                started_at=started,
                status="running",
            )
            session.add(audit)
            await session.commit()

            try:
                affected = await async_core(session)
                audit.status = "succeeded"
            except Exception as e:
                error = f"{type(e).__name__}: {e}"
                audit.status = "failed"
                audit.error = error[:2000]
                log.exception("scheduled.failed", job=job_name)
            finally:
                audit.affected_count = affected
                audit.finished_at = datetime.now(timezone.utc)
                await session.commit()
    finally:
        await engine.dispose()

    return {"job": job_name, "affected": affected, "error": error}
