"""Telegram Business Bot adapter — Sprint 3.4 G2.

Bot Mode: Telegram Business — a Premium user attaches the bot to their
business account and the bot then mirrors inbound client chats. The
webhook delivers either:

  * `message`           — for chats the bot is in directly.
  * `business_message`  — for client conversations proxied through
                          the manager's Business account. This is the
                          common case for DrinkX.

Both shapes carry the same essentials (text + chat id + message id);
this adapter normalizes them into a `WebhookPayload`.

TODO(sprint-3.5, per-manager bots):
    Right now there is exactly one Telegram bot per CRM installation
    (`TELEGRAM_BOT_TOKEN` in env). Each manager will eventually attach
    their own bot via Settings → channels, the same way Gmail is
    connected today. Migration path:
      1. Store token + secret per (workspace_id, user_id) in
         `channel_connections` (channel_type='telegram'), reusing the
         encrypted-credentials path from app.inbox.crypto.
      2. Webhook URL becomes `/api/webhooks/telegram/{connection_id}`
         so each bot's traffic routes to the right manager.
      3. `_resolve_workspace_id` falls away — workspace + manager are
         read from the ChannelConnection row matched by the URL.
      4. `TelegramAdapter` takes a ChannelConnection in __init__ and
         pulls the token from there; `DEFAULT_WORKSPACE_ID` retires.
    Until then, the single-bot path here is the MVP.
"""
from __future__ import annotations

import httpx
import structlog

from app.config import get_settings
from app.inbox.schemas import OutboundMessage, WebhookPayload

log = structlog.get_logger()


_API_BASE = "https://api.telegram.org"


class TelegramAdapter:
    """Implements `ChannelAdapter` for Telegram Bot / Business API."""

    channel = "telegram"

    def __init__(self, *, bot_token: str | None = None) -> None:
        s = get_settings()
        self.bot_token = bot_token if bot_token is not None else s.telegram_bot_token

    # ------------------------------------------------------------------
    # Inbound
    # ------------------------------------------------------------------

    async def parse_webhook(self, raw: dict) -> WebhookPayload:
        """Normalize Telegram Update JSON into a WebhookPayload.

        Tolerant of missing keys — Telegram routinely omits fields for
        non-text payloads (stickers, contacts, etc.). We coerce to
        empty strings and let the matcher decide what to do.
        """
        # Telegram Business proxy uses `business_message`; direct bot
        # DMs use `message`. Same shape modulo a `business_connection_id`
        # on the business variant.
        msg = raw.get("business_message") or raw.get("message") or {}

        chat = msg.get("chat") or {}
        from_ = msg.get("from") or {}

        chat_id = chat.get("id") or from_.get("id")
        sender_id = str(chat_id) if chat_id is not None else None

        body = msg.get("text") or msg.get("caption") or ""

        message_id = msg.get("message_id")
        external_id = f"tg_{message_id}" if message_id is not None else None

        # Contact share — Telegram includes a `contact` object with
        # phone_number. We forward that as `sender_id` ONLY if no chat
        # id (rare); otherwise sender_id stays the chat id and the
        # caller can still inspect `body` for fallback matching.
        if sender_id is None:
            contact = msg.get("contact") or {}
            phone = contact.get("phone_number")
            if phone:
                sender_id = str(phone)

        return WebhookPayload(
            channel="telegram",
            direction="inbound",
            external_id=external_id,
            sender_id=sender_id,
            body=body,
        )

    # ------------------------------------------------------------------
    # Outbound
    # ------------------------------------------------------------------

    async def send(self, msg: OutboundMessage) -> str:
        """Send via Telegram Bot API `sendMessage`.

        Returns Telegram's `message_id` as a string. Raises
        `TelegramSendError` on non-2xx responses so the caller can
        surface a clear error to the UI instead of leaking provider
        internals.
        """
        if not self.bot_token:
            raise TelegramSendError("telegram_bot_token_not_configured")

        url = f"{_API_BASE}/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": msg.recipient_id,
            "text": msg.body,
        }

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(url, json=payload)
        except httpx.HTTPError as exc:
            log.warning(
                "inbox.telegram.send.http_error",
                error=str(exc)[:200],
                recipient=msg.recipient_id,
            )
            raise TelegramSendError("telegram_http_error") from exc

        if resp.status_code != 200:
            log.warning(
                "inbox.telegram.send.bad_status",
                status=resp.status_code,
                body=resp.text[:300],
                recipient=msg.recipient_id,
            )
            raise TelegramSendError(
                f"telegram_status_{resp.status_code}"
            )

        data = resp.json() if resp.content else {}
        result = data.get("result") or {}
        tg_message_id = result.get("message_id")
        if tg_message_id is None:
            raise TelegramSendError("telegram_missing_message_id")
        return f"tg_{tg_message_id}"


class TelegramSendError(Exception):
    """Raised when sending via Telegram Bot API fails. The message is
    a stable error code (`telegram_status_400`, `telegram_http_error`,
    etc.) safe to surface to the UI as `detail`."""
