"""Website-leads inbox — read model over FormSubmission.

A single section that lists ONLY form/website submissions (not the whole
lead base), newest first, with the joined lead + form context the inbox
UI needs. The "new" state is per-user: a submission is new when it was
created after the caller's `users.forms_inbox_seen_at`.

The inbox is a to-do list, not an archive: a submission stays only while
its lead is alive and still on the first stage of its pipeline. Once a
manager moves the lead on (or closes / deletes it) it leaves the inbox;
the history lives on the lead card and in /today stats.

Kept separate from `repositories.py` because this is a cross-form read
model (joins submissions ⋈ forms ⋈ leads ⋈ assignee), distinct from the
per-form CRUD the repository handles.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.forms.lead_factory import (
    extract_person_name,
    extract_question,
    extract_summary,
)
from app.forms.models import FormSubmission, WebForm
from app.leads.models import Lead
from app.pipelines.models import Stage


def _pending(q):
    """Keep only submissions still waiting for a manager (see module doc)."""
    first_position = (
        select(func.min(Stage.position))
        .where(Stage.pipeline_id == Lead.pipeline_id)
        .correlate(Lead)
        .scalar_subquery()
    )
    return (
        q.join(Lead, FormSubmission.lead_id == Lead.id)
        .outerjoin(Stage, Lead.stage_id == Stage.id)
        .where(
            Lead.deleted_at.is_(None),
            (Lead.stage_id.is_(None)) | (Stage.position == first_position),
        )
    )


async def count_new(
    session: AsyncSession, *, workspace_id: uuid.UUID, seen_at: datetime | None
) -> int:
    """Badge count: submissions in the workspace newer than `seen_at`
    (all of them when the user has never opened the inbox)."""
    q = (
        select(func.count())
        .select_from(FormSubmission)
        .join(WebForm, FormSubmission.web_form_id == WebForm.id)
        .where(WebForm.workspace_id == workspace_id)
    )
    q = _pending(q)
    if seen_at is not None:
        q = q.where(FormSubmission.created_at > seen_at)
    return int((await session.execute(q)).scalar_one() or 0)


async def list_inbox(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    seen_at: datetime | None,
    form_id: uuid.UUID | None = None,
    unseen_only: bool = False,
    page: int = 1,
    page_size: int = 30,
) -> tuple[list[dict[str, Any]], int]:
    """Return (items, total). Each item is a flat dict the router maps to
    `InboxItemOut`. Newest first."""
    page = max(page, 1)
    page_size = max(min(page_size, 100), 1)
    offset = (page - 1) * page_size

    base = _pending(
        select(FormSubmission, WebForm, Lead, User.name)
        .join(WebForm, FormSubmission.web_form_id == WebForm.id)
        .where(WebForm.workspace_id == workspace_id)
    ).join(User, Lead.assigned_to == User.id, isouter=True)
    if form_id is not None:
        base = base.where(FormSubmission.web_form_id == form_id)
    if unseen_only and seen_at is not None:
        base = base.where(FormSubmission.created_at > seen_at)

    # Total (mirror the same filters, count submissions only).
    count_q = _pending(
        select(func.count())
        .select_from(FormSubmission)
        .join(WebForm, FormSubmission.web_form_id == WebForm.id)
        .where(WebForm.workspace_id == workspace_id)
    )
    if form_id is not None:
        count_q = count_q.where(FormSubmission.web_form_id == form_id)
    if unseen_only and seen_at is not None:
        count_q = count_q.where(FormSubmission.created_at > seen_at)
    total = int((await session.execute(count_q)).scalar_one() or 0)

    rows = await session.execute(
        base.order_by(FormSubmission.created_at.desc()).offset(offset).limit(page_size)
    )

    items: list[dict[str, Any]] = []
    for sub, form, lead, assignee_name in rows.all():
        is_new = seen_at is None or sub.created_at > seen_at
        items.append(
            {
                "submission_id": sub.id,
                "lead_id": sub.lead_id,
                "created_at": sub.created_at,
                "is_new": is_new,
                "contact_name": extract_person_name(sub.raw_payload),
                "question": extract_question(sub.raw_payload),
                "summary": extract_summary(sub.raw_payload),
                "source_domain": sub.source_domain,
                "utm_json": sub.utm_json,
                # form context
                "form_id": form.id,
                "form_name": form.name,
                "form_slug": form.slug,
                "channel": form.source_label or form.name,
                "company_name": lead.company_name,
                "phone": lead.phone,
                "email": lead.email,
                "assignment_status": lead.assignment_status,
                "assignee_name": assignee_name,
            }
        )
    return items, total


__all__ = ["count_new", "list_inbox"]
