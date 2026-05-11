"""Channel webhook entry points — Sprint 3.4.

These endpoints are called by Telegram / MAX / Mango directly. Auth is
done per-provider:

  * Telegram: `X-Telegram-Bot-Api-Secret-Token` header == our secret.
  * MAX: TBD G3.
  * Mango: HMAC `sign` over the JSON payload (G4).

Webhook handlers MUST return 2xx whenever the message was accepted —
provider retries on non-2xx and that creates duplicate records, even
though we have a UNIQUE INDEX guard. We only return non-2xx for
authentication failures.
"""
from __future__ import annotations

import json
import secrets
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Workspace
from app.config import get_settings
from app.db import get_db
from app.inbox import message_services
from app.inbox.adapters.phone import PhoneAdapter, compute_sign
from app.inbox.adapters.telegram import TelegramAdapter

log = structlog.get_logger()

webhooks_router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


# ---------------------------------------------------------------------------
# Workspace resolution
# ---------------------------------------------------------------------------

async def _resolve_workspace_id(session: AsyncSession) -> UUID | None:
    """Pick which workspace a webhook-delivered message belongs to.

    Order:
      1. `settings.default_workspace_id` if set (multi-tenant override).
      2. The only workspace in the DB (single-tenant DrinkX install).

    Returns None only if the DB has zero workspaces (boot-only edge).

    TODO(sprint-3.5, per-manager bots): once Telegram bots live in
    `channel_connections` (one per manager, like Gmail), workspace +
    manager are read from the ChannelConnection identified by the
    webhook URL path. This shim retires then.
    """
    s = get_settings()
    if s.default_workspace_id:
        try:
            return UUID(s.default_workspace_id)
        except ValueError:
            log.warning(
                "inbox.webhook.bad_default_workspace_id",
                value=s.default_workspace_id[:64],
            )
    res = await session.execute(select(Workspace.id).limit(1))
    return res.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

@webhooks_router.post("/telegram", include_in_schema=False)
async def telegram_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_telegram_bot_api_secret_token: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    """Telegram Business Bot webhook.

    Auth: `X-Telegram-Bot-Api-Secret-Token` header (set via setWebhook).
    Returns 200 on success so Telegram does not retry, 401 on bad secret.
    """
    s = get_settings()
    if not s.telegram_webhook_secret:
        log.error("inbox.webhook.telegram.no_secret_configured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="telegram_webhook_not_configured",
        )

    presented = x_telegram_bot_api_secret_token or ""
    if not secrets.compare_digest(presented, s.telegram_webhook_secret):
        log.warning("inbox.webhook.telegram.bad_secret")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_secret",
        )

    raw = await request.json()

    adapter = TelegramAdapter()
    try:
        payload = await adapter.parse_webhook(raw)
    except Exception as exc:  # noqa: BLE001 — never let Telegram retry on a parse bug
        log.exception("inbox.webhook.telegram.parse_failed", error=str(exc)[:200])
        return {"status": "ignored"}

    workspace_id = await _resolve_workspace_id(db)
    if workspace_id is None:
        log.error("inbox.webhook.telegram.no_workspace")
        return {"status": "ignored"}

    await message_services.receive(
        db, workspace_id=workspace_id, payload=payload
    )
    await db.commit()
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Mango Office (phone)
# ---------------------------------------------------------------------------

@webhooks_router.post("/phone", include_in_schema=False)
async def phone_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    """Mango VPBX webhook for call_end / missed_call events.

    Mango sends `application/x-www-form-urlencoded` with at minimum:
      * `vpbx_api_key` — our key
      * `sign`         — hex sha256(api_key + json + api_salt)
      * `json`         — JSON-encoded event payload OR raw fields

    Auth is validated only when `mango_api_salt` is configured —
    leaving it blank is the documented dev path (sign validation
    short-circuits with a once-per-startup warning).
    """
    s = get_settings()
    form = await request.form()
    presented_sign = str(form.get("sign") or "")
    json_field = form.get("json")

    # The event payload may come either inline in a `json` field OR as
    # individual top-level form fields. Try `json` first; fall back to
    # the form itself minus the auth pair.
    if json_field:
        try:
            raw = json.loads(json_field)
        except ValueError:
            log.warning("inbox.webhook.phone.bad_json")
            return {"status": "ignored"}
        signed_blob = str(json_field)
    else:
        raw = {k: v for k, v in form.items() if k not in ("vpbx_api_key", "sign")}
        signed_blob = json.dumps(raw, separators=(",", ":"), ensure_ascii=False, sort_keys=True)

    if s.mango_api_salt:
        expected = compute_sign(
            s.mango_api_key, signed_blob, s.mango_api_salt
        )
        if not presented_sign or not secrets.compare_digest(
            presented_sign, expected
        ):
            log.warning("inbox.webhook.phone.bad_sign")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid_sign",
            )
    else:
        # Dev / pre-creds path. Log once so the operator can't miss it.
        log.warning("inbox.webhook.phone.unsigned_accepted")

    adapter = PhoneAdapter()
    try:
        payload = await adapter.parse_webhook(raw)
    except Exception as exc:  # noqa: BLE001
        log.exception("inbox.webhook.phone.parse_failed", error=str(exc)[:200])
        return {"status": "ignored"}

    workspace_id = await _resolve_workspace_id(db)
    if workspace_id is None:
        log.error("inbox.webhook.phone.no_workspace")
        return {"status": "ignored"}

    await message_services.receive(
        db, workspace_id=workspace_id, payload=payload
    )
    await db.commit()
    return {"status": "ok"}
