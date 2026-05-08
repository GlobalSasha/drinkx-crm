"""WebForms service layer — Sprint 2.2 G1.

`create_form` re-tries on slug collision (the unique index on
`web_forms.slug` will surface IntegrityError; the random suffix is
strong enough that one retry is overkill but cheap insurance).
"""
from __future__ import annotations

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


_MAX_SLUG_RETRIES = 3


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
) -> WebForm:
    """Persist a new form. Auto-generates the slug from `name`; retries
    on the rare slug collision (random suffix keeps this near-zero in
    practice). Caller commits."""
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
