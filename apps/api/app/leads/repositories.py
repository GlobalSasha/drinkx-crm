"""Leads data-access layer — SQLAlchemy 2.0 async."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import and_, func, nullslast, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from app.contacts.models import Contact
from app.followups.models import Followup
from app.leads.models import Lead

log = structlog.get_logger()


# Reminder kinds that count as «задача» (manual work) vs «followup»
# (automated touch). Pre-flight decision — see Sprint spec.
_TASK_KINDS = ("manager",)
_FOLLOWUP_KINDS = ("auto_email", "ai_hint")


def parse_form_slug_from_source(source: str | None) -> str | None:
    """Extract the form slug from `lead.source` if it carries one.

    `lead_factory.create_lead_from_submission` writes
    `source = f"form:{slug}"` for form-originated leads. Returns the
    slug (no prefix) or None for non-form / malformed sources.
    """
    if not source:
        return None
    prefix = "form:"
    if not source.startswith(prefix):
        return None
    slug = source[len(prefix):].strip()
    return slug or None


async def resolve_form_for_source(
    db: AsyncSession, source: str | None
) -> tuple[uuid.UUID, str] | None:
    """Look up the WebForm by slug parsed from `source`. Returns
    (form_id, form_name) or None when the source is not a form or the
    form has been deleted (FK SET NULL on the foreign key path)."""
    slug = parse_form_slug_from_source(source)
    if slug is None:
        return None

    from app.forms.models import WebForm

    result = await db.execute(
        select(WebForm.id, WebForm.name).where(WebForm.slug == slug).limit(1)
    )
    row = result.first()
    if row is None:
        return None
    return (row[0], row[1])


async def latest_form_utm_for_lead(
    db: AsyncSession, lead_id: uuid.UUID
) -> dict | None:
    """Return the UTM dict from the most recent `form_submission`
    Activity for the lead, or None when no such Activity exists."""
    from app.activity.models import Activity

    result = await db.execute(
        select(Activity.payload_json)
        .where(Activity.lead_id == lead_id, Activity.type == "form_submission")
        .order_by(Activity.created_at.desc())
        .limit(1)
    )
    payload = result.scalar_one_or_none()
    if not payload:
        return None
    utm = payload.get("utm") if isinstance(payload, dict) else None
    if not utm or not isinstance(utm, dict):
        return None
    return dict(utm)


def _open_count_subquery(reminder_kinds: tuple[str, ...]):
    """Return a correlated SELECT COUNT(*) of Followup rows for a lead
    whose status != 'done' and reminder_kind is in the given set.
    Wrapping as a scalar subquery in the SELECT list — one round-trip,
    no N+1."""
    return (
        select(func.count(Followup.id))
        .where(Followup.lead_id == Lead.id)
        .where(Followup.status != "done")
        .where(Followup.reminder_kind.in_(reminder_kinds))
        .correlate(Lead)
        .scalar_subquery()
    )


async def _resolve_forms_batch(
    db: AsyncSession, slugs: list[str]
) -> dict[str, tuple[uuid.UUID, str]]:
    """One SELECT to resolve a list of form slugs → {slug: (form_id, form_name)}.

    Used by the list path so the whole page costs one query instead of N.
    """
    if not slugs:
        return {}

    from app.forms.models import WebForm

    result = await db.execute(
        select(WebForm.slug, WebForm.id, WebForm.name).where(
            WebForm.slug.in_(slugs)
        )
    )
    return {row[0]: (row[1], row[2]) for row in result.all()}


async def _latest_utms_batch(
    db: AsyncSession, lead_ids: list[uuid.UUID]
) -> dict[uuid.UUID, dict]:
    """One SELECT DISTINCT ON (lead_id) to get the latest form_submission
    UTM payload for each lead. Returns {lead_id: utm_dict}.

    Used by the list path so the whole page costs one query instead of N.
    """
    if not lead_ids:
        return {}

    from app.activity.models import Activity

    result = await db.execute(
        select(Activity.lead_id, Activity.payload_json)
        .where(
            Activity.lead_id.in_(lead_ids),
            Activity.type == "form_submission",
        )
        .distinct(Activity.lead_id)
        .order_by(Activity.lead_id, Activity.created_at.desc())
    )
    utms: dict[uuid.UUID, dict] = {}
    for lead_id, payload in result.all():
        if not payload or not isinstance(payload, dict):
            continue
        utm = payload.get("utm")
        if utm and isinstance(utm, dict):
            utms[lead_id] = dict(utm)
    return utms


async def _populate_extras(
    rows: list,
    *,
    db: AsyncSession | None = None,
) -> list[Lead]:
    """Walk the (Lead, primary_contact_name, open_tasks, open_followups)
    tuples and attach the joined values to the Lead instance so the
    Pydantic schema can read them as if they were ORM columns.

    Sprint 3.6: also resolves `source_form_id`/`source_form_name` via
    a batched WebForm query and `latest_utm` via a single batched
    form_submission Activity query. Both are best-effort — if the form
    was deleted or the Activity row is missing, the fields stay None. A
    transient DB error is caught and logged rather than surfacing a 500.
    """
    leads: list[Lead] = []
    for lead, contact_name, open_tasks, open_followups in rows:
        lead.primary_contact_name = contact_name  # type: ignore[attr-defined]
        lead.open_tasks_count = open_tasks  # type: ignore[attr-defined]
        lead.open_followups_count = open_followups  # type: ignore[attr-defined]
        # Defaults so Pydantic doesn't complain even if `db` is None.
        lead.source_form_id = None  # type: ignore[attr-defined]
        lead.source_form_name = None  # type: ignore[attr-defined]
        lead.latest_utm = None  # type: ignore[attr-defined]
        leads.append(lead)

    if db is not None:
        try:
            # ── Batch 1: resolve form slugs → (form_id, form_name) ──────────
            slug_to_lead: dict[str, list[Lead]] = {}
            for lead in leads:
                slug = parse_form_slug_from_source(lead.source)
                if slug is not None:
                    slug_to_lead.setdefault(slug, []).append(lead)

            if slug_to_lead:
                form_map = await _resolve_forms_batch(db, list(slug_to_lead.keys()))
                for slug, form_leads in slug_to_lead.items():
                    if slug in form_map:
                        form_id, form_name = form_map[slug]
                        for lead in form_leads:
                            lead.source_form_id = form_id  # type: ignore[attr-defined]
                            lead.source_form_name = form_name  # type: ignore[attr-defined]

            # ── Batch 2: fetch latest UTMs for form-sourced leads ────────────
            form_lead_ids = [
                lead.id for lead in leads if lead.source_form_id is not None
            ]
            if form_lead_ids:
                utm_map = await _latest_utms_batch(db, form_lead_ids)
                for lead in leads:
                    if lead.id in utm_map:
                        lead.latest_utm = utm_map[lead.id]  # type: ignore[attr-defined]
        except Exception:
            log.warning(
                "leads.enrich.error",
                lead_count=len(leads),
                exc_info=True,
            )
            # Fields remain at None defaults — don't crash the list response.

    return leads


async def get_by_id(db: AsyncSession, lead_id: uuid.UUID, workspace_id: uuid.UUID) -> Lead | None:
    """Fetch a single lead with primary-contact name + open work counts.

    The Lead Card needs the same 4 extra fields the list view does
    (`primary_contact_name`, `open_tasks_count`, `open_followups_count`,
    plus the resolved `primary_contact_id` from the row). We attach
    them onto the ORM instance so Pydantic `from_attributes=True`
    serializes them transparently."""
    stmt = (
        select(
            Lead,
            Contact.name.label("primary_contact_name"),
            _open_count_subquery(_TASK_KINDS).label("open_tasks_count"),
            _open_count_subquery(_FOLLOWUP_KINDS).label("open_followups_count"),
        )
        .select_from(Lead)
        .outerjoin(Contact, Contact.id == Lead.primary_contact_id)
        .where(Lead.id == lead_id, Lead.workspace_id == workspace_id)
    )
    row = (await db.execute(stmt)).first()
    if row is None:
        return None
    populated = await _populate_extras([row], db=db)
    return populated[0]


async def list_leads(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    *,
    stage_id: uuid.UUID | None = None,
    pipeline_id: uuid.UUID | None = None,
    segment: str | None = None,
    city: str | None = None,
    priority: str | None = None,
    deal_type: str | None = None,
    assigned_to: uuid.UUID | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[Lead], int]:
    """Return (rows, total) — only assignment_status='assigned' leads.

    Sprint 2.3 G2: pipeline_id filter scopes the result set to one
    voronka. The /pipeline switcher passes the user-selected pipeline
    id; /today and /leads-pool intentionally don't filter and keep
    aggregating across all of the user's pipelines.
    """
    base = select(Lead).where(
        Lead.workspace_id == workspace_id,
        Lead.assignment_status == "assigned",
    )
    if stage_id is not None:
        base = base.where(Lead.stage_id == stage_id)
    if pipeline_id is not None:
        base = base.where(Lead.pipeline_id == pipeline_id)
    if segment is not None:
        base = base.where(Lead.segment == segment)
    if city is not None:
        base = base.where(Lead.city == city)
    if priority is not None:
        base = base.where(Lead.priority == priority)
    if deal_type is not None:
        base = base.where(Lead.deal_type == deal_type)
    if assigned_to is not None:
        base = base.where(Lead.assigned_to == assigned_to)
    if q is not None:
        base = base.where(Lead.company_name.ilike(f"%{q}%"))

    count_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total: int = count_result.scalar_one()

    # Add primary contact name + open-task/followup counts to each row
    # via LEFT JOIN + correlated scalar subqueries. One round-trip, no
    # N+1 across the page. `defer()` skips heavy JSONB columns that
    # the list response doesn't include (ai_data, agent_state).
    list_stmt = (
        base.add_columns(
            Contact.name.label("primary_contact_name"),
            _open_count_subquery(_TASK_KINDS).label("open_tasks_count"),
            _open_count_subquery(_FOLLOWUP_KINDS).label("open_followups_count"),
        )
        .outerjoin(Contact, Contact.id == Lead.primary_contact_id)
        .options(defer(Lead.ai_data), defer(Lead.agent_state))
        .order_by(Lead.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows_result = await db.execute(list_stmt)
    return await _populate_extras(list(rows_result.all()), db=db), total


async def list_pool(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    *,
    city: str | None = None,
    segment: str | None = None,
    fit_min: float | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[Lead], int]:
    """Return pool leads ordered by fit_score DESC NULLS LAST, created_at ASC."""
    base = select(Lead).where(
        Lead.workspace_id == workspace_id,
        Lead.assignment_status == "pool",
    )
    if city is not None:
        base = base.where(Lead.city == city)
    if segment is not None:
        base = base.where(Lead.segment == segment)
    if fit_min is not None:
        base = base.where(Lead.fit_score >= fit_min)

    count_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total: int = count_result.scalar_one()

    list_stmt = (
        base.add_columns(
            Contact.name.label("primary_contact_name"),
            _open_count_subquery(_TASK_KINDS).label("open_tasks_count"),
            _open_count_subquery(_FOLLOWUP_KINDS).label("open_followups_count"),
        )
        .outerjoin(Contact, Contact.id == Lead.primary_contact_id)
        .options(defer(Lead.ai_data), defer(Lead.agent_state))
        .order_by(nullslast(Lead.fit_score.desc()), Lead.created_at.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows_result = await db.execute(list_stmt)
    return await _populate_extras(list(rows_result.all()), db=db), total


async def create_lead(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    payload: dict[str, Any],
    *,
    assigned_to: uuid.UUID | None = None,
    assignment_status: str = "assigned",
) -> Lead:
    now = datetime.now(timezone.utc)
    lead = Lead(
        workspace_id=workspace_id,
        assignment_status=assignment_status,
        assigned_to=assigned_to,
        assigned_at=now if assigned_to else None,
        **payload,
    )
    db.add(lead)
    await db.flush()
    await db.refresh(lead)
    return lead


async def update_lead(db: AsyncSession, lead: Lead, patch_dict: dict[str, Any]) -> Lead:
    for field, value in patch_dict.items():
        setattr(lead, field, value)
    await db.flush()
    await db.refresh(lead)
    return lead


async def delete_lead(db: AsyncSession, lead: Lead) -> None:
    await db.delete(lead)
    await db.flush()


async def claim_lead(
    db: AsyncSession,
    lead_id: uuid.UUID,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Lead | None:
    """Race-safe atomic UPDATE — returns None if already claimed."""
    stmt = (
        update(Lead)
        .where(
            Lead.id == lead_id,
            Lead.workspace_id == workspace_id,
            Lead.assignment_status == "pool",
        )
        .values(
            assigned_to=user_id,
            assigned_at=func.now(),
            assignment_status="assigned",
        )
        .returning(Lead)
    )
    result = await db.execute(stmt)
    await db.flush()
    return result.scalar_one_or_none()


async def unclaim_lead(
    db: AsyncSession,
    lead_id: uuid.UUID,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Lead | None:
    """Atomic UPDATE that returns a lead to the pool. Returns None if the
    lead isn't assigned to `user_id` (so callers can surface a 403/404).
    """
    stmt = (
        update(Lead)
        .where(
            Lead.id == lead_id,
            Lead.workspace_id == workspace_id,
            Lead.assigned_to == user_id,
            Lead.assignment_status == "assigned",
        )
        .values(
            assigned_to=None,
            assigned_at=None,
            assignment_status="pool",
        )
        .returning(Lead)
    )
    result = await db.execute(stmt)
    await db.flush()
    return result.scalar_one_or_none()


async def claim_sprint(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    cities: list[str],
    segment: str | None = None,
    limit: int = 20,
) -> list[Lead]:
    """Race-safe N-claim using FOR UPDATE SKIP LOCKED."""
    # Step 1: select candidate IDs (SKIP LOCKED avoids blocking concurrent sprints)
    where_parts = [
        "workspace_id = :workspace_id",
        "assignment_status = 'pool'",
    ]
    params: dict[str, Any] = {"workspace_id": workspace_id, "limit": limit}

    if cities:
        where_parts.append("city = ANY(:cities)")
        params["cities"] = cities

    if segment is not None:
        where_parts.append("segment = :segment")
        params["segment"] = segment

    where_clause = " AND ".join(where_parts)
    sql = text(
        f"SELECT id FROM leads WHERE {where_clause} "
        "ORDER BY fit_score DESC NULLS LAST, created_at ASC "
        "LIMIT :limit FOR UPDATE SKIP LOCKED"
    )
    id_result = await db.execute(sql, params)
    candidate_ids = [row[0] for row in id_result.fetchall()]

    # Step 2: claim each candidate individually (only if still pool)
    claimed: list[Lead] = []
    for lead_id in candidate_ids:
        stmt = (
            update(Lead)
            .where(Lead.id == lead_id, Lead.assignment_status == "pool")
            .values(
                assigned_to=user_id,
                assigned_at=func.now(),
                assignment_status="assigned",
            )
            .returning(Lead)
        )
        result = await db.execute(stmt)
        lead = result.scalar_one_or_none()
        if lead is not None:
            claimed.append(lead)

    await db.flush()
    return claimed


async def transfer_lead(
    db: AsyncSession,
    lead: Lead,
    to_user_id: uuid.UUID,
    comment: str | None = None,  # noqa: ARG001 — stored in activity log (Task 4)
) -> Lead:
    """Transfer ownership, recording the previous assignee.

    Acquires a row-level lock on `leads` before the write so two
    concurrent transfers on the same lead serialize — without this,
    `transferred_from` can be lost (the second writer reads the row
    after the first has already overwritten `assigned_to`)."""
    now = datetime.now(timezone.utc)
    # SELECT … FOR UPDATE the lead row. Lock is released at txn commit.
    locked = await db.execute(
        select(Lead).where(Lead.id == lead.id).with_for_update()
    )
    fresh = locked.scalar_one()
    fresh.transferred_from = fresh.assigned_to
    fresh.transferred_at = now
    fresh.assigned_to = to_user_id
    fresh.assigned_at = now
    fresh.assignment_status = "assigned"
    await db.flush()
    await db.refresh(fresh)
    return fresh
