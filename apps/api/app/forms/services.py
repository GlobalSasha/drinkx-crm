"""WebForms service layer — Sprint 2.2 G1.

`create_form` re-tries on slug collision (the unique index on
`web_forms.slug` will surface IntegrityError; the random suffix is
strong enough that one retry is overkill but cheap insurance).
"""
from __future__ import annotations

import secrets
import uuid
from typing import Any

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.forms import repositories as repo
from app.forms.models import WebForm
from app.forms.slug import generate_slug

log = structlog.get_logger()


class WebFormNotFound(Exception):
    pass


class WebFormInvalidTarget(Exception):
    """Sprint 2.3 G1 carryover from 2.2: target_pipeline_id /
    target_stage_id must belong to the form's workspace, and the stage
    must be a child of the pipeline. Router maps to HTTP 400."""


_MAX_SLUG_RETRIES = 3


async def _validate_target(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    target_pipeline_id: uuid.UUID | None,
    target_stage_id: uuid.UUID | None,
) -> None:
    """Workspace-scope check on the form's target placement. Both
    fields are nullable — if the manager omits them, the public submit
    falls back to `repositories.get_default_first_stage`. But IF a
    value is supplied, it must be inside the form's workspace; the
    stage must be a child of the pipeline.

    Without this guard a malicious admin could craft a form whose
    `target_pipeline_id` points at another workspace's pipeline,
    leaking submissions across the boundary on every public POST."""
    from app.pipelines import repositories as pipelines_repo
    from app.pipelines.models import Pipeline

    if target_pipeline_id is None and target_stage_id is None:
        return

    if target_stage_id is not None and target_pipeline_id is None:
        raise WebFormInvalidTarget(
            "target_stage_id requires target_pipeline_id"
        )

    # Pipeline must exist + belong to this workspace.
    from sqlalchemy import select

    result = await session.execute(
        select(Pipeline.id)
        .where(
            Pipeline.id == target_pipeline_id,
            Pipeline.workspace_id == workspace_id,
        )
        .limit(1)
    )
    if result.scalar_one_or_none() is None:
        raise WebFormInvalidTarget(
            "target_pipeline_id does not belong to this workspace"
        )

    # Stage must be a child of the named pipeline.
    if target_stage_id is not None:
        ok = await pipelines_repo.stage_belongs_to_pipeline(
            session,
            stage_id=target_stage_id,
            pipeline_id=target_pipeline_id,  # type: ignore[arg-type]
        )
        if not ok:
            raise WebFormInvalidTarget(
                "target_stage_id is not a stage of target_pipeline_id"
            )


async def _assignee_in_workspace(
    session: AsyncSession, *, user_id: uuid.UUID, workspace_id: uuid.UUID
) -> bool:
    from sqlalchemy import select

    from app.auth.models import User

    res = await session.execute(
        select(User.id).where(User.id == user_id, User.workspace_id == workspace_id).limit(1)
    )
    return res.scalar_one_or_none() is not None


async def create_form(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID | None,
    name: str,
    fields_json: list[dict[str, Any]],
    target_pipeline_id: uuid.UUID | None = None,
    target_stage_id: uuid.UUID | None = None,
    redirect_url: str | None = None,
    default_assignee_id: uuid.UUID | None = None,
    contact_task_sla_hours: int = 2,
    source_label: str | None = None,
    notify_email: str | None = None,
    require_key: bool = False,
    autoreply_enabled: bool = False,
    autoreply_subject: str | None = None,
    autoreply_body: str | None = None,
) -> WebForm:
    """Persist a new form. Auto-generates the slug from `name`; retries
    on the rare slug collision (random suffix keeps this near-zero in
    practice). Caller commits.

    Sprint 2.3 G1 carryover: validates that target_pipeline_id +
    target_stage_id (if supplied) belong to the form's workspace —
    raises WebFormInvalidTarget on a cross-workspace reference.
    """
    await _validate_target(
        session,
        workspace_id=workspace_id,
        target_pipeline_id=target_pipeline_id,
        target_stage_id=target_stage_id,
    )

    if default_assignee_id is not None:
        if not await _assignee_in_workspace(session, user_id=default_assignee_id, workspace_id=workspace_id):
            raise WebFormInvalidTarget("default_assignee_id does not belong to this workspace")
    ingest_token = secrets.token_urlsafe(32) if require_key else None

    last_error: Exception | None = None
    for attempt in range(_MAX_SLUG_RETRIES):
        slug = generate_slug(name)
        try:
            form = await repo.create(
                session,
                workspace_id=workspace_id,
                created_by=user_id,
                name=name[:200],
                slug=slug,
                fields_json=[
                    f.model_dump() if hasattr(f, "model_dump") else f
                    for f in (fields_json or [])
                ],
                target_pipeline_id=target_pipeline_id,
                target_stage_id=target_stage_id,
                redirect_url=redirect_url,
                default_assignee_id=default_assignee_id,
                contact_task_sla_hours=contact_task_sla_hours,
                source_label=source_label,
                notify_email=notify_email,
                ingest_token=ingest_token,
                autoreply_enabled=autoreply_enabled,
                autoreply_subject=autoreply_subject,
                autoreply_body=autoreply_body,
            )
            return form
        except IntegrityError as exc:
            last_error = exc
            await session.rollback()
            log.warning(
                "webforms.slug_collision_retry",
                attempt=attempt,
                slug=slug,
            )
    # Out of retries — re-raise so the caller sees a real failure.
    assert last_error is not None
    raise last_error


async def get_form_or_404(
    session: AsyncSession,
    *,
    form_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> WebForm:
    form = await repo.get_by_id(
        session, form_id=form_id, workspace_id=workspace_id
    )
    if form is None:
        raise WebFormNotFound(str(form_id))
    return form


async def update_form(
    session: AsyncSession,
    *,
    form_id: uuid.UUID,
    workspace_id: uuid.UUID,
    patch: dict[str, Any],
) -> WebForm:
    form = await get_form_or_404(
        session, form_id=form_id, workspace_id=workspace_id
    )
    cleaned: dict[str, Any] = {}
    for k, v in patch.items():
        if v is None and k != "is_active":
            # Treat None as "leave alone" except for is_active where
            # None still means "leave alone" — we can't disambiguate
            # PATCH-omit from PATCH-with-null in HTTP, so we use the
            # presence of the key in the input dict.
            continue
        if k == "fields_json" and v is not None:
            cleaned[k] = [
                f.model_dump() if hasattr(f, "model_dump") else f for f in v
            ]
        else:
            cleaned[k] = v
    if not cleaned:
        return form

    # Sprint 2.3 G1 carryover: re-validate target if either field is
    # being touched. Reads the patch values when present, falls back
    # to the form's existing values so a partial PATCH stays
    # consistent (manager flips only the stage → still must live in
    # the existing pipeline).
    target_pipeline_id = cleaned.get("target_pipeline_id", form.target_pipeline_id)
    target_stage_id = cleaned.get("target_stage_id", form.target_stage_id)
    if (
        "target_pipeline_id" in cleaned
        or "target_stage_id" in cleaned
    ):
        await _validate_target(
            session,
            workspace_id=workspace_id,
            target_pipeline_id=target_pipeline_id,
            target_stage_id=target_stage_id,
        )

    if cleaned.get("default_assignee_id") is not None:
        if not await _assignee_in_workspace(
            session, user_id=cleaned["default_assignee_id"], workspace_id=workspace_id
        ):
            raise WebFormInvalidTarget("default_assignee_id does not belong to this workspace")
    if "require_key" in cleaned:
        rk = cleaned.pop("require_key")
        if rk and not form.ingest_token:
            # Enable protection: generate a key only if there isn't one yet.
            cleaned["ingest_token"] = secrets.token_urlsafe(32)
        elif not rk:
            # Disable protection: clear the key.
            cleaned["ingest_token"] = None
        # rk True + token already exists → leave the token untouched (no silent rotation).

    return await repo.update(session, form=form, patch=cleaned)


async def delete_form(
    session: AsyncSession,
    *,
    form_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> WebForm:
    form = await get_form_or_404(
        session, form_id=form_id, workspace_id=workspace_id
    )
    return await repo.soft_delete(session, form=form)


async def rotate_key(
    session: AsyncSession,
    *,
    form_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> WebForm:
    form = await get_form_or_404(session, form_id=form_id, workspace_id=workspace_id)
    if not form.ingest_token:
        raise WebFormInvalidTarget("form has no ingest key to rotate; enable require_key first")
    form.ingest_token = secrets.token_urlsafe(32)
    await session.flush()
    return form


async def get_form_stats(
    db: AsyncSession,
    *,
    form_id: uuid.UUID,
) -> "FormStatsOut":
    """Aggregate per-form metrics for the admin /forms stats card.

    Four queries instead of one CTE — each is trivially cheap because
    `form_submissions` is indexed on `web_form_id` and the counts hit
    that index directly. Ordering matters: 7d → 30d → claimed → by_stage
    to mirror the tests.
    """
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import func, select

    from app.forms.models import FormSubmission
    from app.forms.schemas import FormStatsOut
    from app.leads.models import Lead
    from app.pipelines.models import Stage

    now = datetime.now(timezone.utc)
    cutoff_7d = now - timedelta(days=7)
    cutoff_30d = now - timedelta(days=30)

    r_7d = await db.execute(
        select(func.count()).select_from(FormSubmission).where(
            FormSubmission.web_form_id == form_id,
            FormSubmission.created_at >= cutoff_7d,
        )
    )
    r_30d = await db.execute(
        select(func.count()).select_from(FormSubmission).where(
            FormSubmission.web_form_id == form_id,
            FormSubmission.created_at >= cutoff_30d,
        )
    )

    # `claimed` = distinct leads (via submissions) that have been taken
    # out of pool. DISTINCT guards against hypothetical duplicate rows;
    # explicit IS NOT NULL mirrors spec and makes the NULL exclusion
    # intentional rather than implicit via INNER JOIN.
    r_claimed = await db.execute(
        select(func.count(FormSubmission.lead_id.distinct()))
        .select_from(FormSubmission)
        .join(Lead, Lead.id == FormSubmission.lead_id)
        .where(
            FormSubmission.web_form_id == form_id,
            FormSubmission.lead_id.isnot(None),
            Lead.assignment_status == "assigned",
        )
    )

    # LEFT OUTER JOIN so leads with stage_id=NULL are not silently
    # excluded — they surface under "Без этапа" instead of vanishing.
    r_stage = await db.execute(
        select(
            func.coalesce(Stage.name, "Без этапа").label("stage_name"),
            func.count(Lead.id),
        )
        .select_from(FormSubmission)
        .join(Lead, Lead.id == FormSubmission.lead_id)
        .outerjoin(Stage, Stage.id == Lead.stage_id)
        .where(FormSubmission.web_form_id == form_id)
        .group_by(func.coalesce(Stage.name, "Без этапа"))
    )

    return FormStatsOut(
        submissions_7d=int(r_7d.scalar_one() or 0),
        submissions_30d=int(r_30d.scalar_one() or 0),
        claimed_count=int(r_claimed.scalar_one() or 0),
        by_stage={name: int(count) for name, count in r_stage.all()},
    )


async def get_channel_analytics(db, *, workspace_id, date_from=None, date_to=None):
    from app.forms.schemas import FormAnalyticsOut, FormChannelStat

    raw = await repo.channel_analytics(
        db, workspace_id=workspace_id, date_from=date_from, date_to=date_to
    )
    rows = []
    for r in raw:
        leads = int(r["leads"] or 0)
        won = int(r["won"] or 0)
        rows.append(FormChannelStat(
            form_id=r["form_id"], channel=r["channel"],
            submissions=int(r["submissions"] or 0), leads=leads, won=won,
            conversion=round(won / leads, 4) if leads else 0.0,
        ))
    return FormAnalyticsOut(
        rows=rows,
        total_submissions=sum(x.submissions for x in rows),
        total_leads=sum(x.leads for x in rows),
        total_won=sum(x.won for x in rows),
    )
