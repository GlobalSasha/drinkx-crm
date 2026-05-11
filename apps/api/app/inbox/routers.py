"""Inbox REST — Gmail OAuth + listing + confirm/dismiss (Sprint 2.0 G1+G4)."""
from __future__ import annotations

import json
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.auth.models import User
from app.config import get_settings
from app.db import get_db
from app.inbox import message_services
from app.inbox import oauth as oauth_helpers
from app.inbox import services as inbox_services
from app.inbox.crypto import encrypt_credentials
from app.inbox.models import ChannelConnection
from app.inbox.schemas import (
    InboxCallIn,
    InboxCallOut,
    InboxConfirmIn,
    InboxCountOut,
    InboxFeedOut,
    InboxItemOut,
    InboxMessageAssignIn,
    InboxMessageOut,
    InboxPageOut,
    InboxSendIn,
    InboxUnmatchedMessagesOut,
)

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
    # Encrypt at-rest if FERNET_KEY is configured; falls back to plaintext
    # in stub mode (with a startup-once WARNING — see app/inbox/crypto.py).
    creds_json_str = encrypt_credentials(json.dumps(creds_payload))

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


# ---------------------------------------------------------------------------
# G4 — listing / confirm / dismiss
# ---------------------------------------------------------------------------

@router.get("", response_model=InboxPageOut)
async def list_inbox(
    item_status: Annotated[str, Query(alias="status")] = "pending",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> InboxPageOut:
    """Paginated InboxItem list, scoped to caller's workspace."""
    items, total = await inbox_services.list_inbox(
        db,
        workspace_id=user.workspace_id,
        status=item_status,
        page=page,
        page_size=page_size,
    )
    return InboxPageOut(
        items=[InboxItemOut.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/count", response_model=InboxCountOut)
async def count_inbox(
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> InboxCountOut:
    """Pending count — drives the sidebar badge (polled every 30s)."""
    n = await inbox_services.count_pending(db, workspace_id=user.workspace_id)
    return InboxCountOut(pending=n)


@router.post("/{item_id}/confirm", response_model=InboxItemOut)
async def confirm_inbox_item(
    item_id: UUID,
    payload: InboxConfirmIn,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> InboxItemOut:
    """Resolve a pending InboxItem via match_lead / create_lead / add_contact."""
    try:
        item = await inbox_services.confirm_item(
            db,
            item_id=item_id,
            user_id=user.id,
            workspace_id=user.workspace_id,
            action=payload.action,
            lead_id=payload.lead_id,
            company_name=payload.company_name,
            contact_name=payload.contact_name,
        )
    except inbox_services.InboxItemNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    except inbox_services.InboxItemBadRequest as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        )
    return InboxItemOut.model_validate(item)


@router.post("/{item_id}/dismiss", response_model=InboxItemOut)
async def dismiss_inbox_item(
    item_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> InboxItemOut:
    try:
        item = await inbox_services.dismiss_item(
            db,
            item_id=item_id,
            user_id=user.id,
            workspace_id=user.workspace_id,
        )
    except inbox_services.InboxItemNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    return InboxItemOut.model_validate(item)


# ---------------------------------------------------------------------------
# Sprint 3.4 G1 — messenger / phone inbox
# ---------------------------------------------------------------------------

@router.get("/unmatched/messages", response_model=InboxUnmatchedMessagesOut)
async def list_unmatched_messages(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> InboxUnmatchedMessagesOut:
    """Inbox messages (tg / max / phone) with no matched lead."""
    items, total = await message_services.list_unmatched_messages(
        db,
        workspace_id=user.workspace_id,
        page=page,
        page_size=page_size,
    )
    return InboxUnmatchedMessagesOut(
        items=[InboxMessageOut.model_validate(m) for m in items],
        total=total,
    )


@router.patch("/messages/{message_id}/assign", response_model=InboxMessageOut)
async def assign_unmatched_message(
    message_id: UUID,
    payload: InboxMessageAssignIn,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> InboxMessageOut:
    try:
        msg = await message_services.assign(
            db,
            workspace_id=user.workspace_id,
            message_id=message_id,
            lead_id=payload.lead_id,
        )
    except message_services.InboxMessageNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="not_found"
        )
    except message_services.InboxMessageBadRequest as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        )
    return InboxMessageOut.model_validate(msg)


# ---------------------------------------------------------------------------
# Sprint 3.4 G1 — lead-scoped merged inbox feed
#
# Mounted under `/leads/{lead_id}/inbox` to match the existing lead-scoped
# convention (cf. app.contacts.routers, app.leads.routers). The leads
# router prefix is `/leads`, so this sub-router fits naturally next to it.
# ---------------------------------------------------------------------------

lead_inbox_router = APIRouter(
    prefix="/leads/{lead_id}/inbox", tags=["inbox"]
)


@lead_inbox_router.get("", response_model=InboxFeedOut)
async def lead_inbox_feed(
    lead_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> InboxFeedOut:
    """Merged feed: email (inbox_items) + messenger/phone (inbox_messages)."""
    return await message_services.list_for_lead(
        db,
        workspace_id=user.workspace_id,
        lead_id=lead_id,
    )


@lead_inbox_router.post("/call", response_model=InboxCallOut)
async def lead_inbox_call(
    lead_id: UUID,
    payload: InboxCallIn,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> InboxCallOut:
    """Click-to-call via Mango — asks the PBX to bridge the manager's
    extension with the lead's phone number. The actual call log lands
    via the inbound `call_end` webhook minutes later.
    """
    try:
        result = await message_services.place_call(
            db,
            workspace_id=user.workspace_id,
            lead_id=lead_id,
            from_extension=payload.from_extension,
            manager_user_id=user.id,
        )
    except message_services.InboxMessageNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="lead_not_found"
        )
    except message_services.InboxMessageBadRequest as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        )
    except message_services.InboxSendError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        )
    return InboxCallOut(
        status=str(result.get("status", "dialing")),
        detail=result if isinstance(result, dict) else None,
    )


@lead_inbox_router.post("/send", response_model=InboxMessageOut)
async def lead_inbox_send(
    lead_id: UUID,
    payload: InboxSendIn,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> InboxMessageOut:
    """Send a message from the lead card.

    Sprint 3.4 G2: telegram. G3: max. G4: phone (click-to-call gets
    its own endpoint). G5: email (Gmail send).
    """
    try:
        msg = await message_services.send(
            db,
            workspace_id=user.workspace_id,
            lead_id=lead_id,
            channel=payload.channel,
            body=payload.body,
            manager_user_id=user.id,
        )
    except message_services.InboxMessageNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="lead_not_found"
        )
    except message_services.InboxMessageBadRequest as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        )
    except message_services.InboxSendError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        )
    return InboxMessageOut.model_validate(msg)
