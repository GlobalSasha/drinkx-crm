"""Settings REST endpoints — Sprint 2.4 G2 + G3.

Surface in /settings:
  GET   /api/settings/channels — Gmail per-user state + SMTP config (G2)
  GET   /api/settings/ai       — workspace AI section (admin) (G3)
  PATCH /api/settings/ai       — flip budget cap / primary model (admin) (G3)

Channels: read-only resolution of already-existing config (Sprint 2.0
ChannelConnection rows + env-var SMTP). AI: resolves env defaults +
workspace overrides into a typed payload, persists overrides in
workspace.settings_json (no migration — JSON column existed since
Sprint 1.1).
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.audit import log as log_audit_event
from app.auth.dependencies import current_user, require_admin
from app.auth.models import User
from app.config import get_settings
from app.db import get_db
from app.inbox.models import ChannelConnection
from app.settings import services as svc
from app.settings.schemas import (
    AISettingsOut,
    AISettingsUpdateIn,
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


# ---------------------------------------------------------------------------
# AI section — Sprint 2.4 G3
# ---------------------------------------------------------------------------


@router.get("/ai", response_model=AISettingsOut)
async def get_ai_settings_endpoint(
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin)] = ...,
) -> AISettingsOut:
    """Return the workspace's AI configuration.

    Admin-only — surfaces the daily spend (the budget guard reads the
    same Redis counter so the UI gauge can't drift) plus the chosen
    primary provider. Managers don't need this view; they only see
    enrichment results, not the budget knobs.
    """
    payload = await svc.get_ai_settings(db, workspace_id=user.workspace_id)
    return AISettingsOut.model_validate(payload)


@router.patch("/ai", response_model=AISettingsOut)
async def update_ai_settings_endpoint(
    payload: AISettingsUpdateIn,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
    user: Annotated[User, Depends(require_admin)] = ...,
) -> AISettingsOut:
    """Update the workspace's AI configuration. Admin-only."""
    try:
        result = await svc.update_ai_settings(
            db,
            workspace_id=user.workspace_id,
            daily_budget_usd=payload.daily_budget_usd,
            primary_model=payload.primary_model,
        )
    except svc.InvalidAIModel as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "invalid_model",
                "message": f"Неизвестная модель: {exc}",
            },
        ) from exc
    except svc.InvalidBudget as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "invalid_budget",
                "message": "Бюджет не может быть отрицательным.",
            },
        ) from exc

    await log_audit_event(
        db,
        workspace_id=user.workspace_id,
        user_id=user.id,
        action="settings.ai_change",
        entity_type="workspace",
        entity_id=user.workspace_id,
        delta={
            "daily_budget_usd": payload.daily_budget_usd,
            "primary_model": payload.primary_model,
        },
    )
    await db.commit()
    return AISettingsOut.model_validate(result)
