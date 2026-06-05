"""Website-leads inbox — read model over FormSubmission.

A single section that lists ONLY form/website submissions (not the whole
lead base), newest first, with the joined lead + form context the inbox
UI needs. The "new" state is per-user: a submission is new when it was
created after the caller's `users.forms_inbox_seen_at`.

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
from app.forms.models import FormSubmission, WebForm
from app.leads.models import Lead

# Raw-payload keys (RU + EN) that carry the visitor's free-text message.
# Mirrors the lead_factory mapping; first non-empty wins.
_SNIPPET_KEYS = (
    "comment", "comments", "message", "сообщение", "комментарий", "вопрос",
)


def extract_snippet(raw_payload: Any, *, limit: int = 160) -> str:
    """Best-effort one-line preview of the submission for the inbox row."""
    if not isinstance(raw_payload, dict):
        return ""
    for k in _SNIPPET_KEYS:
        v = raw_payload.get(k)
        if v:
            text = " ".join(str(v).split())
            return text[:limit]
    return ""


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

    base = (
        select(FormSubmission, WebForm, Lead, User.name)
        .join(WebForm, FormSubmission.web_form_id == WebForm.id)
        .join(Lead, FormSubmission.lead_id == Lead.id, isouter=True)
        .join(User, Lead.assigned_to == User.id, isouter=True)
        .where(WebForm.workspace_id == workspace_id)
    )
    if form_id is not None:
        base = base.where(FormSubmission.web_form_id == form_id)
    if unseen_only and seen_at is not None:
        base = base.where(FormSubmission.created_at > seen_at)

    # Total (mirror the same filters, count submissions only).
    count_q = (
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
                "snippet": extract_snippet(sub.raw_payload),
                "source_domain": sub.source_domain,
                "utm_json": sub.utm_json,
                # form context
                "form_id": form.id,
                "form_name": form.name,
                "form_slug": form.slug,
                "channel": form.source_label or form.name,
                # lead context (lead may be None if it was hard-deleted)
                "company_name": lead.company_name if lead else None,
                "phone": lead.phone if lead else None,
                "email": lead.email if lead else None,
                "assignment_status": lead.assignment_status if lead else None,
                "assignee_name": assignee_name,
            }
        )
    return items, total


__all__ = ["extract_snippet", "count_new", "list_inbox"]
