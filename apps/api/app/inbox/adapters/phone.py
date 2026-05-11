"""Mango Office VPBX adapter — Sprint 3.4 G4.

Telephony in DrinkX is a two-way bridge with Mango Office:

  * Inbound: Mango POSTs call_end / missed_call events to
    `/api/webhooks/phone`. We parse them into a `WebhookPayload` and
    let the matcher attach the call to a Lead by normalized phone
    number. Answered calls with a `recording_url` trigger a
    transcription Celery task (G4b).

  * Outbound: the manager clicks the phone icon in the lead card and
    we call Mango's VPBX command endpoint to bridge their desk
    extension to the lead's number. This adapter exposes
    `initiate_call(from_extension, to_number)` for that; the canonical
    log entry arrives back on the inbound webhook ~minutes later.

Signing: Mango uses
    sign = sha256(vpbx_api_key + json + api_salt)
for both the outbound commands and the inbound webhook payloads. The
exact field names vary slightly between Mango VPBX versions; we keep
the algorithm in `compute_sign` so a future Sprint can tweak it
without touching the rest of the code.
"""
from __future__ import annotations

import hashlib
import json as _json

import httpx
import structlog

from app.config import get_settings
from app.inbox.schemas import OutboundMessage, WebhookPayload

log = structlog.get_logger()


# Mango maps several direction strings to the same logical case; we
# fold them into our inbound / outbound axis.
_INBOUND_DIRECTIONS = {"in", "incoming", "from_client", "to_employee"}
_OUTBOUND_DIRECTIONS = {"out", "outgoing", "from_employee", "to_client"}


def compute_sign(api_key: str, json_body: str, api_salt: str) -> str:
    """Mango VPBX signature: hex-sha256 of `api_key + json + api_salt`."""
    h = hashlib.sha256()
    h.update(api_key.encode("utf-8"))
    h.update(json_body.encode("utf-8"))
    h.update(api_salt.encode("utf-8"))
    return h.hexdigest()


class MangoCallError(Exception):
    """Outbound call failed. The message is a stable code
    (`mango_status_400`, `mango_http_error`, `mango_not_configured`)
    safe to surface as `detail` to the UI."""


class PhoneAdapter:
    """Implements the messenger half of `ChannelAdapter` for Mango.

    Click-to-call is exposed via `initiate_call` (NOT `send`, because
    a phone call has no body); the protocol's `send` is therefore
    deliberately unimplemented — `message_services.send` re-routes
    `channel='phone'` to `place_call` instead.
    """

    channel = "phone"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_salt: str | None = None,
        api_base: str | None = None,
    ) -> None:
        s = get_settings()
        self.api_key = api_key if api_key is not None else s.mango_api_key
        self.api_salt = api_salt if api_salt is not None else s.mango_api_salt
        self.api_base = (api_base or s.mango_api_base).rstrip("/")

    # ------------------------------------------------------------------
    # Inbound webhook
    # ------------------------------------------------------------------

    async def parse_webhook(self, raw: dict) -> WebhookPayload:
        """Normalize Mango call_end / missed_call into a WebhookPayload.

        Field-by-field:
          * `event` ∈ {call_end, missed_call} (optional — we infer from
            call_duration when missing)
          * `call_id` / `entry_id` — used as external_id for dedup
          * `direction` / `disposition` — normalized to inbound/outbound
          * `from` / `from_number` and `to` / `to_number` — bare digits
          * `call_duration` — integer seconds (0 on missed)
          * `recording_url` — link to the .mp3 (may be empty)
        """
        duration_raw = raw.get("call_duration", 0)
        try:
            duration = int(duration_raw or 0)
        except (TypeError, ValueError):
            duration = 0

        raw_dir = str(raw.get("direction") or raw.get("disposition") or "").lower()
        if raw_dir in _OUTBOUND_DIRECTIONS:
            direction = "outbound"
        else:
            direction = "inbound"  # default — Mango omits direction on inbound calls in some setups

        if direction == "inbound":
            caller = raw.get("from") or raw.get("from_number")
        else:
            caller = raw.get("to") or raw.get("to_number")

        event = str(raw.get("event") or "").lower()
        if event == "missed_call" or duration <= 0:
            call_status = "missed"
            body = "Пропущенный звонок"
        else:
            call_status = "answered"
            mins, secs = divmod(duration, 60)
            label = "Входящий" if direction == "inbound" else "Исходящий"
            body = f"{label} звонок, {mins}:{secs:02d}"

        external_id = raw.get("call_id") or raw.get("entry_id")
        if external_id is not None:
            external_id = str(external_id)

        return WebhookPayload(
            channel="phone",
            direction=direction,
            external_id=external_id,
            sender_id=str(caller) if caller is not None else None,
            body=body,
            media_url=raw.get("recording_url") or None,
            call_duration=duration if duration > 0 else None,
            call_status=call_status,
        )

    # ------------------------------------------------------------------
    # Outbound — click-to-call
    # ------------------------------------------------------------------

    async def initiate_call(
        self, *, from_extension: str, to_number: str
    ) -> dict:
        """Bridge `from_extension` (manager's internal line) with the
        lead's phone number via Mango's callback command.

        Returns the parsed Mango response on success. Raises
        `MangoCallError` with a stable code on failure.
        """
        if not self.api_key or not self.api_salt:
            raise MangoCallError("mango_not_configured")

        cmd_id = f"drinkx-{from_extension}-{to_number}"
        body = {
            "command_id": cmd_id,
            "from": {"extension": str(from_extension)},
            "to_number": str(to_number),
        }
        json_body = _json.dumps(body, separators=(",", ":"), ensure_ascii=False)
        sign = compute_sign(self.api_key, json_body, self.api_salt)

        url = f"{self.api_base}/vpbx/commands/callback"
        form = {
            "vpbx_api_key": self.api_key,
            "sign": sign,
            "json": json_body,
        }

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(url, data=form)
        except httpx.HTTPError as exc:
            log.warning(
                "inbox.phone.initiate.http_error",
                error=str(exc)[:200],
                to=to_number,
            )
            raise MangoCallError("mango_http_error") from exc

        if resp.status_code != 200:
            log.warning(
                "inbox.phone.initiate.bad_status",
                status=resp.status_code,
                body=resp.text[:300],
                to=to_number,
            )
            raise MangoCallError(f"mango_status_{resp.status_code}")

        try:
            return resp.json() if resp.content else {"status": "dialing"}
        except ValueError:
            return {"status": "dialing", "raw": resp.text[:300]}

    # ------------------------------------------------------------------
    # ChannelAdapter Protocol — send is not used for phone.
    # ------------------------------------------------------------------

    async def send(self, msg: OutboundMessage) -> str:  # pragma: no cover — intentional
        raise NotImplementedError(
            "phone channel uses initiate_call (click-to-call), not send"
        )
