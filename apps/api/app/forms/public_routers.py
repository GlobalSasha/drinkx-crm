"""Public unauthed endpoints for the WebForms domain — Sprint 2.2 G2.

Lives on a distinct prefix `/api/public/forms/` so:
  - the slug-based routing here doesn't collide with the admin
    `/api/forms/{form_id: UUID}` paths
  - the path-aware CORS middleware (see app/main.py) can grant
    wildcard origins ONLY for `/api/public/*` without loosening
    the rest of the API

No auth dependency. Rate-limited per (slug, IP) via Redis.
"""
from __future__ import annotations

from typing import Annotated, Any
from urllib.parse import urlparse

import structlog
from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.forms import repositories as repo
from app.forms.embed import generate_embed_js
from app.forms.lead_factory import create_lead_from_submission
from app.forms.models import FormSubmission
from app.forms.rate_limit import check_rate_limit
# Module-level import: the binary-mode Redis client (no decode_responses)
# is also used by the export blob storage. Importing at module load time
# rather than lazily in the handler keeps the public_routers
# `app.import_export.redis_bytes.get_bytes_redis` patch target valid in
# tests (string-based patch needs the dotted path resolvable on import).
from app.import_export.redis_bytes import get_bytes_redis

log = structlog.get_logger()

public_router = APIRouter(prefix="/api/public/forms", tags=["forms_public"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_UTM_KEYS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_content",
    "utm_term",
}


def _client_ip(request: Request) -> str:
    """Best-effort client-IP extraction. Honours X-Forwarded-For when
    nginx is in front (production setup); falls back to direct
    connection for local dev. Trims to the first hop — XFF can
    chain through multiple proxies and the leftmost is the original
    client."""
    xff = request.headers.get("x-forwarded-for") or ""
    if xff:
        return xff.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return ""


def _source_domain(request: Request) -> str | None:
    """Strip protocol + path + leading www. from the Referer header."""
    referer = request.headers.get("referer") or request.headers.get("referrer")
    if not referer:
        return None
    try:
        netloc = urlparse(referer).netloc.lower()
    except Exception:  # noqa: BLE001
        return None
    if not netloc:
        return None
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc[:300]


def _extract_utm(payload: dict[str, Any]) -> dict[str, str]:
    """Pull UTM values from the submitted body. The embed.js helper
    populates these from `window.location.search`, but a manager
    hand-wiring the form may set them as hidden fields too."""
    out: dict[str, str] = {}
    for k in _UTM_KEYS:
        v = payload.get(k)
        if v:
            out[k] = str(v)[:200]
    return out


async def _notify_workspace_admins(
    session: AsyncSession,
    *,
    workspace_id,
    form_name: str,
    company_name: str,
    lead_id,
) -> None:
    """Fire-and-forget admin notifications. Wrapped here so a
    notification storm or DB hiccup never bubbles up to the public
    submit response."""
    from sqlalchemy import select

    from app.auth.models import User
    from app.notifications.services import safe_notify

    try:
        res = await session.execute(
            select(User.id)
            .where(User.workspace_id == workspace_id)
            .where(User.role == "admin")
        )
        for (admin_id,) in res.all():
            await safe_notify(
                session,
                workspace_id=workspace_id,
                user_id=admin_id,
                kind="system",
                title="Новая заявка с формы",
                body=f'"{form_name}" — {company_name}',
                lead_id=lead_id,
            )
    except Exception as exc:  # noqa: BLE001 — public flow must not 5xx
        log.warning(
            "forms.admin_notify_failed",
            form_name=form_name,
            error=str(exc)[:200],
        )


# ---------------------------------------------------------------------------
# POST /submit
# ---------------------------------------------------------------------------

@public_router.post("/{slug}/submit")
async def submit_form(
    slug: str,
    request: Request,
    payload: Annotated[dict[str, Any], Body(...)],
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
) -> dict[str, Any]:
    settings = get_settings()
    ip = _client_ip(request)

    redis_client = get_bytes_redis()
    allowed = await check_rate_limit(
        redis_client,
        ip=ip,
        slug=slug,
        limit=settings.form_rate_limit_per_minute,
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Слишком много заявок с этого IP. Попробуйте через минуту.",
        )

    form = await repo.get_by_slug(db, slug=slug)
    if form is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Форма не найдена",
        )
    if not form.is_active:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Форма больше не принимает заявки",
        )

    src_domain = _source_domain(request)
    utm = _extract_utm(payload)

    # Lead creation
    try:
        lead = await create_lead_from_submission(
            db,
            form=form,
            payload=payload,
            source_domain=src_domain,
        )
    except Exception as exc:  # noqa: BLE001 — surface as 500 with safe detail
        log.exception("forms.lead_creation_failed", slug=slug)
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось создать лид. Попробуйте позже.",
        ) from exc

    # Submission record + counter increment
    submission = FormSubmission(
        web_form_id=form.id,
        lead_id=lead.id,
        raw_payload=payload,
        utm_json=utm or None,
        source_domain=src_domain,
        ip=ip[:45] if ip else None,
    )
    db.add(submission)
    await repo.increment_submissions_count(db, form=form)

    await db.commit()
    await db.refresh(form)
    await db.refresh(lead)

    # Notify admins — best-effort, runs in a fresh sub-routine so a
    # commit failure here doesn't undo the lead/submission writes.
    await _notify_workspace_admins(
        db,
        workspace_id=form.workspace_id,
        form_name=form.name,
        company_name=lead.company_name,
        lead_id=lead.id,
    )
    try:
        await db.commit()
    except Exception:  # noqa: BLE001
        pass

    return {"ok": True, "redirect": form.redirect_url}


# ---------------------------------------------------------------------------
# GET /embed.js
# ---------------------------------------------------------------------------

@public_router.get("/{slug}/embed.js")
async def get_embed_js(
    slug: str,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
) -> Response:
    form = await repo.get_by_slug(db, slug=slug)
    if form is None:
        # Return a JS-shaped 404 so a forgotten slug doesn't crash a
        # landing page's <script> error handler with HTML.
        return Response(
            content="// drinkx-form: form not found\n",
            media_type="application/javascript; charset=utf-8",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if not form.is_active:
        return Response(
            content="// drinkx-form: this form is no longer accepting submissions\n",
            media_type="application/javascript; charset=utf-8",
            status_code=status.HTTP_410_GONE,
        )

    settings = get_settings()
    body = generate_embed_js(form, api_base_url=settings.api_base_url)
    return Response(
        content=body,
        media_type="application/javascript; charset=utf-8",
        headers={
            # 5-min cache — busts via the auto-generated slug suffix when
            # the form definition is rewritten; manager doesn't have to
            # remember to bump a version param.
            "Cache-Control": "public, max-age=300",
        },
    )


__all__ = ["public_router"]
