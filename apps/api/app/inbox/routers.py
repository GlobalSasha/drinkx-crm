"""Inbox REST — Gmail OAuth start + callback (Sprint 2.0 G1).

Group 4 will add /api/inbox listing + confirm/dismiss endpoints.
"""
from __future__ import annotations

import json
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.auth.models import User
from app.config import get_settings
from app.db import get_db
from app.inbox import oauth as oauth_helpers
from app.inbox.models import ChannelConnection

log = structlog.get_logger()

router = APIRouter(prefix="/api/inbox", tags=["inbox"])


@router.post("/connect-gmail")
async def connect_gmail(
    user: Annotated[User, Depends(current_user)],
) -> dict[str, str]:
    """Start the Gmail OAuth flow.

    Returns a `redirect_url` that the SPA opens in the same tab. After the
    user approves, Google redirects to /api/inbox/gmail/callback which
    finishes the flow and bounces the browser to /inbox.
    """
    s = get_settings()
    if not s.google_client_id or not s.google_client_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="google_oauth_not_configured",
        )
    state = oauth_helpers.sign_state(user.id)
    consent_url = oauth_helpers.build_consent_url(state)
    return {"redirect_url": consent_url}


@router.get("/gmail/callback")
async def gmail_callback(
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
) -> RedirectResponse:
    """OAuth callback from Google.

    NOTE: this endpoint cannot use `Depends(current_user)` because the
    browser arrives here without our Bearer header. Identity is recovered
    from the signed `state` parameter the caller passed to consent.
    """
    if error:
        return RedirectResponse(
            oauth_helpers.build_post_callback_redirect(success=False, error=error)
        )
    if not code or not state:
        return RedirectResponse(
            oauth_helpers.build_post_callback_redirect(
                success=False, error="missing_code_or_state"
            )
        )

    user_id = oauth_helpers.verify_state(state)
    if user_id is None:
        return RedirectResponse(
            oauth_helpers.build_post_callback_redirect(
                success=False, error="invalid_state"
            )
        )

    user_row = await db.execute(select(User).where(User.id == user_id))
    user = user_row.scalar_one_or_none()
    if user is None:
        return RedirectResponse(
            oauth_helpers.build_post_callback_redirect(
                success=False, error="user_not_found"
            )
        )

    try:
        creds_payload = oauth_helpers.exchange_code_for_credentials(code)
    except Exception as exc:
        log.exception("inbox.gmail_callback.exchange_failed", error=str(exc)[:200])
        return RedirectResponse(
            oauth_helpers.build_post_callback_redirect(
                success=False, error="token_exchange_failed"
            )
        )

    # Upsert per (workspace, user, channel_type='gmail').
    existing = await db.execute(
        select(ChannelConnection).where(
            ChannelConnection.workspace_id == user.workspace_id,
            ChannelConnection.user_id == user.id,
            ChannelConnection.channel_type == "gmail",
        )
    )
    conn = existing.scalar_one_or_none()
    creds_json_str = json.dumps(creds_payload)

    if conn is None:
        conn = ChannelConnection(
            workspace_id=user.workspace_id,
            user_id=user.id,
            channel_type="gmail",
            credentials_json=creds_json_str,
            status="active",
            extra_json={},
        )
        db.add(conn)
    else:
        conn.credentials_json = creds_json_str
        conn.status = "active"
        conn.extra_json = conn.extra_json or {}

    await db.commit()
    await db.refresh(conn)

    # Kick off the historical sync. Group 2 implements
    # gmail_history_sync; until then this is a no-op task name.
    try:
        from app.scheduled.celery_app import celery_app

        celery_app.send_task(
            "app.scheduled.jobs.gmail_history_sync",
            args=[str(user.id)],
        )
    except Exception as exc:
        log.warning("inbox.gmail_history_sync.dispatch_failed", error=str(exc)[:200])

    return RedirectResponse(
        oauth_helpers.build_post_callback_redirect(success=True)
    )
