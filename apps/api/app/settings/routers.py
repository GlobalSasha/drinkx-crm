"""Settings REST endpoints — Sprint 2.4 G2.

Read-only views the admin needs in /settings → «Каналы»:
  GET /api/settings/channels — Gmail per-user state + SMTP config.

Both pieces of data already live in the system (ChannelConnection
table + app.config.Settings). This endpoint just resolves them
into a single payload the frontend can render. No new persistent
storage; no DB-backed SMTP credentials in v1 (Sprint 2.4 NOT-ALLOWED).
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import current_user
from app.auth.models import User
from app.config import get_settings
from app.db import get_db
from app.inbox.models import ChannelConnection
from app.settings.schemas import (
    ChannelsStatusOut,
    GmailChannelOut,
    SmtpConfigOut,
)

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/channels", response_model=ChannelsStatusOut)
async def get_channels_status(
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(current_user)] = ...,
) -> ChannelsStatusOut:
    """Resolve Gmail (per-user) + SMTP (workspace-wide config) into
    a single read-only payload for the Settings → «Каналы» panel.

    All roles read this — sensitive bits (SMTP password, OAuth
    tokens) are never serialized. Roles are an aesthetic question
    here, not a security one: managers seeing «SMTP via env» is
    fine.
    """
    s = get_settings()

    # ---- Gmail ----------------------------------------------------------
    # `configured`: server has the OAuth client credentials. If False,
    # «Подключить» CTA still renders but POST /api/inbox/connect-gmail
    # would return 503 (graceful empty-key path). Surfacing this lets
    # the UI render «Заполните GOOGLE_CLIENT_ID на сервере» instead
    # of leaving the button silent like Sprint 2.0 known issue #7.
    gmail_configured = bool(s.google_client_id and s.google_client_secret)

    # `connected`: the current user has an active ChannelConnection
    # row. Per ADR-019 + Sprint 2.0 ownership decision, Gmail
    # channels are per-user, not workspace-wide.
    res = await db.execute(
        select(ChannelConnection).where(
            ChannelConnection.user_id == user.id,
            ChannelConnection.channel_type == "gmail",
            ChannelConnection.status == "active",
        )
    )
    conn = res.scalar_one_or_none()

    gmail = GmailChannelOut(
        configured=gmail_configured,
        connected=conn is not None,
        last_sync_at=conn.last_sync_at if conn else None,
    )

    # ---- SMTP -----------------------------------------------------------
    # Stub mode while host is empty (Sprint 1.5 pattern). When stub
    # mode is on, the daily digest cron renders the email but logs
    # it to stdout instead of sending. Surfacing this in the UI
    # tells the admin «выходящие письма пока не отправляются».
    smtp = SmtpConfigOut(
        configured=bool(s.smtp_host),
        host=s.smtp_host,
        port=s.smtp_port,
        from_address=s.smtp_from,
        user=s.smtp_user,
    )

    return ChannelsStatusOut(gmail=gmail, smtp=smtp)
