"""WebForms data access — SQLAlchemy 2.0 async."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.forms.models import FormSubmission, WebForm


async def create(session: AsyncSession, **kwargs: Any) -> WebForm:
    row = WebForm(**kwargs)
    session.add(row)
    await session.flush()  # surface IntegrityError on slug collision pre-commit
    return row


async def get_by_id(
    session: AsyncSession, *, form_id: uuid.UUID, workspace_id: uuid.UUID
) -> WebForm | None:
    res = await session.execute(
        select(WebForm)
        .where(WebForm.id == form_id)
        .where(WebForm.workspace_id == workspace_id)
    )
    return res.scalar_one_or_none()


async def get_by_slug(session: AsyncSession, *, slug: str) -> WebForm | None:
    """Public submit / embed.js use this — slug is globally unique so
    no workspace filter needed."""
    res = await session.execute(select(WebForm).where(WebForm.slug == slug))
    return res.scalar_one_or_none()


async def list_for_workspace(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    is_active: bool | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[WebForm], int]:
    page = max(page, 1)
    page_size = max(min(page_size, 100), 1)
    offset = (page - 1) * page_size

    base = select(WebForm).where(WebForm.workspace_id == workspace_id)
    if is_active is not None:
        base = base.where(WebForm.is_active.is_(is_active))

    total_q = (
        select(func.count())
        .select_from(WebForm)
        .where(WebForm.workspace_id == workspace_id)
    )
    if is_active is not None:
        total_q = total_q.where(WebForm.is_active.is_(is_active))
    total = int((await session.execute(total_q)).scalar_one() or 0)

    rows = await session.execute(
        base.order_by(WebForm.created_at.desc()).offset(offset).limit(page_size)
    )
    return list(rows.scalars()), total


async def update(
    session: AsyncSession, *, form: WebForm, patch: dict[str, Any]
) -> WebForm:
    for k, v in patch.items():
        setattr(form, k, v)
    await session.flush()
    return form


async def soft_delete(session: AsyncSession, *, form: WebForm) -> WebForm:
    form.is_active = False
    await session.flush()
    return form


async def increment_submissions_count(
    session: AsyncSession, *, form: WebForm
) -> None:
    """Called from the public submit handler (Group 2). Atomic increment
    avoids the read-modify-write race when two submissions land in the
    same millisecond."""
    form.submissions_count = (form.submissions_count or 0) + 1
    await session.flush()


async def list_submissions(
    session: AsyncSession,
    *,
    form_id: uuid.UUID,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[FormSubmission], int]:
    page = max(page, 1)
    page_size = max(min(page_size, 100), 1)
    offset = (page - 1) * page_size

    base = select(FormSubmission).where(FormSubmission.web_form_id == form_id)
    total = int(
        (
            await session.execute(
                select(func.count())
                .select_from(FormSubmission)
                .where(FormSubmission.web_form_id == form_id)
            )
        ).scalar_one()
        or 0
    )
    rows = await session.execute(
        base.order_by(FormSubmission.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    return list(rows.scalars()), total
