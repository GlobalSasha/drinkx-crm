"""Messenger / phone inbox services — Sprint 3.4 G1 skeleton, G2 expand.

This module mediates between channel adapters and the `inbox_messages`
table. The surface:

  * `normalize_phone`            — pure utility for E.164-ish numbers.
  * `match_lead`                 — webhook payload → Lead.id or None.
  * `receive`                    — idempotent upsert from webhook payload.
                                   Also writes an Activity row when matched
                                   and schedules a Lead Agent refresh on
                                   matched inbound messages.
  * `send`                       — outbound: dispatch via channel adapter,
                                   persist InboxMessage (direction=outbound)
                                   and a matching Activity.
  * `list_for_lead`              — merged feed (inbox_items + inbox_messages).
  * `list_unmatched_messages`    — InboxMessage rows with lead_id IS NULL.
  * `assign`                     — set inbox_messages.lead_id (PATCH).
"""
from __future__ import annotations

import re
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.activity.models import Activity
from app.inbox.models import InboxItem, InboxMessage
from app.inbox.schemas import (
    InboxFeedChannelLink,
    InboxFeedEntry,
    InboxFeedOut,
    OutboundMessage,
    WebhookPayload,
)
from app.leads.models import Lead

log = structlog.get_logger()


class InboxMessageNotFound(Exception):
    pass


class InboxMessageBadRequest(Exception):
    pass


class InboxSendError(Exception):
    """Adapter-side failure surfaced from `send`. The message is a
    stable error code (`telegram_status_400`, `recipient_not_set`,
    ...) safe to expose to the UI as `detail`."""


# `Activity.type` is a String column, not a DB enum, so we are free
# to coin new strings here without a migration. Keep them tight.
_ACTIVITY_TYPE_BY_CHANNEL = {
    "telegram": "tg",
    "max": "max",
    "phone": "phone",
}


def _activity_type_for(channel: str) -> str:
    return _ACTIVITY_TYPE_BY_CHANNEL.get(channel, "system")


# ---------------------------------------------------------------------------
# Pure utilities
# ---------------------------------------------------------------------------

_PHONE_NON_DIGIT_RE = re.compile(r"\D")


def normalize_phone(p: str | None) -> str:
    """Strip everything except digits; collapse RU leading 7/8 to 10 digits.

    The Mango / Telegram payloads use `+7...`, `8(916)...`, `+7 916 ...`
    inconsistently. Storage in `leads.phone` is just as messy. We
    normalize to bare digits for comparison; leads.phone keeps its
    original formatting.
    """
    if not p:
        return ""
    digits = _PHONE_NON_DIGIT_RE.sub("", p)
    if len(digits) == 11 and digits[0] in ("7", "8"):
        digits = digits[1:]
    return digits


# ---------------------------------------------------------------------------
# Lead matching
# ---------------------------------------------------------------------------

async def match_lead(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    payload: WebhookPayload,
) -> UUID | None:
    """Find the Lead this webhook belongs to. Order:

      1. Channel-specific id (`tg_chat_id`, `max_user_id`)
      2. Normalized phone (for phone channel, or messenger that shared number)
      3. None → unmatched

    Returns lead_id or None. Does not raise.
    """
    sender_id = (payload.sender_id or "").strip()
    if not sender_id:
        return None

    if payload.channel == "telegram":
        res = await session.execute(
            select(Lead.id)
            .where(Lead.workspace_id == workspace_id)
            .where(Lead.tg_chat_id == sender_id)
            .limit(1)
        )
        hit = res.scalar_one_or_none()
        if hit is not None:
            return hit

    elif payload.channel == "max":
        res = await session.execute(
            select(Lead.id)
            .where(Lead.workspace_id == workspace_id)
            .where(Lead.max_user_id == sender_id)
            .limit(1)
        )
        hit = res.scalar_one_or_none()
        if hit is not None:
            return hit

    # Phone fallback — also covers messenger users who shared their number
    # via Telegram's `contact` payload. Cheap because we only scan leads
    # in the same workspace that actually have a phone set.
    norm = normalize_phone(sender_id)
    if norm:
        res = await session.execute(
            select(Lead.id, Lead.phone)
            .where(Lead.workspace_id == workspace_id)
            .where(Lead.phone.is_not(None))
        )
        for lead_id, lead_phone in res.all():
            if normalize_phone(lead_phone) == norm:
                return lead_id

    return None


# ---------------------------------------------------------------------------
# Receive (idempotent upsert)
# ---------------------------------------------------------------------------

async def receive(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    payload: WebhookPayload,
) -> tuple[InboxMessage, bool]:
    """Persist an inbound webhook payload.

    Returns (message, created) where `created` is False when the same
    `(channel, external_id)` already existed — dedup for retried
    webhook deliveries. The DB also enforces this via the UNIQUE INDEX
    `uq_inbox_msg_external`; the Python-level pre-check just keeps
    error noise out of the logs.
    """
    if payload.external_id:
        existing = await session.execute(
            select(InboxMessage)
            .where(InboxMessage.channel == payload.channel)
            .where(InboxMessage.external_id == payload.external_id)
            .limit(1)
        )
        prior = existing.scalar_one_or_none()
        if prior is not None:
            return prior, False

    lead_id = await match_lead(
        session, workspace_id=workspace_id, payload=payload
    )

    msg = InboxMessage(
        workspace_id=workspace_id,
        lead_id=lead_id,
        channel=payload.channel,
        direction=payload.direction,
        external_id=payload.external_id,
        sender_id=payload.sender_id,
        body=payload.body,
        media_url=payload.media_url,
        call_duration=payload.call_duration,
        call_status=payload.call_status,
    )
    session.add(msg)
    await session.flush()

    # Matched inbound — fan out side effects (Activity + Lead Agent kick).
    # Outbound rows are written by `send` which records its own Activity
    # so the manager's action shows up immediately.
    if lead_id is not None:
        session.add(
            Activity(
                lead_id=lead_id,
                user_id=None,  # inbound — no manager attribution
                type=_activity_type_for(payload.channel),
                channel=payload.channel,
                direction=payload.direction,
                body=payload.body,
                from_identifier=payload.sender_id,
                payload_json={
                    "inbox_message_id": str(msg.id),
                    "external_id": payload.external_id,
                },
            )
        )
        if payload.direction == "inbound":
            _enqueue_lead_agent_refresh(lead_id, countdown=900)

    # Phone calls that landed with a recording → kick the transcription
    # job (G4b). Missed calls and recording-less rows skip this — there
    # is nothing to transcribe.
    if (
        payload.channel == "phone"
        and payload.call_status == "answered"
        and payload.media_url
    ):
        _enqueue_transcribe(msg.id, countdown=30)

    log.info(
        "inbox.message.received",
        channel=payload.channel,
        direction=payload.direction,
        matched=lead_id is not None,
        external_id=payload.external_id,
    )
    return msg, True


def _enqueue_lead_agent_refresh(lead_id: UUID, *, countdown: int) -> None:
    """Best-effort dispatch — broker hiccups must not break the webhook."""
    try:
        from app.scheduled.jobs import lead_agent_refresh_suggestion

        lead_agent_refresh_suggestion.apply_async(
            args=[str(lead_id)], countdown=countdown
        )
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "inbox.message.lead_agent_refresh_enqueue_failed",
            lead_id=str(lead_id),
            error=str(exc)[:200],
        )


def _enqueue_transcribe(message_id: UUID, *, countdown: int) -> None:
    """Schedule G4b STT on a freshly recorded call. Mango finalizes the
    recording file a few seconds after `call_end` — the countdown
    gives the URL time to become downloadable before the worker hits
    it.
    """
    try:
        from app.scheduled.celery_app import celery_app

        celery_app.send_task(
            "app.scheduled.jobs.transcribe_call",
            args=[str(message_id)],
            countdown=countdown,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "inbox.message.transcribe_enqueue_failed",
            message_id=str(message_id),
            error=str(exc)[:200],
        )


# ---------------------------------------------------------------------------
# Send (G2 Telegram; G3 MAX; G4 phone)
# ---------------------------------------------------------------------------

def _get_adapter(channel: str):
    """Pick the channel adapter. Imports are lazy so the webhook /
    config code-paths don't load a stack we don't use."""
    if channel == "telegram":
        from app.inbox.adapters.telegram import TelegramAdapter

        return TelegramAdapter()
    raise InboxSendError(f"channel_not_supported:{channel}")


def _recipient_for_lead(lead: Lead, channel: str) -> str | None:
    if channel == "telegram":
        return lead.tg_chat_id
    if channel == "max":
        return lead.max_user_id
    if channel == "phone":
        return lead.phone
    return None


async def send(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    lead_id: UUID,
    channel: str,
    body: str,
    manager_user_id: UUID | None = None,
) -> InboxMessage:
    """Send a message on `channel` to the lead's address for that
    channel. Persists an outbound InboxMessage + Activity. Raises
    `InboxMessageNotFound` if the lead is missing,
    `InboxMessageBadRequest` if the recipient address isn't set, and
    `InboxSendError` for adapter failures.
    """
    res = await session.execute(
        select(Lead)
        .where(Lead.id == lead_id)
        .where(Lead.workspace_id == workspace_id)
    )
    lead = res.scalar_one_or_none()
    if lead is None:
        raise InboxMessageNotFound(str(lead_id))

    recipient = _recipient_for_lead(lead, channel)
    if not recipient:
        raise InboxMessageBadRequest(f"recipient_not_set:{channel}")

    adapter = _get_adapter(channel)
    try:
        external_id = await adapter.send(
            OutboundMessage(
                channel=channel,
                recipient_id=str(recipient),
                body=body,
                lead_id=lead_id,
            )
        )
    except Exception as exc:  # noqa: BLE001
        # Adapter raises its own typed errors (e.g. TelegramSendError)
        # — wrap to a stable user-facing code so the UI doesn't depend
        # on provider class names.
        raise InboxSendError(str(exc)) from exc

    msg = InboxMessage(
        workspace_id=workspace_id,
        lead_id=lead_id,
        channel=channel,
        direction="outbound",
        external_id=external_id,
        sender_id=str(recipient),
        body=body,
        manager_user_id=manager_user_id,
    )
    session.add(msg)
    await session.flush()

    session.add(
        Activity(
            lead_id=lead_id,
            user_id=manager_user_id,
            type=_activity_type_for(channel),
            channel=channel,
            direction="outbound",
            body=body,
            to_identifier=str(recipient),
            payload_json={
                "inbox_message_id": str(msg.id),
                "external_id": external_id,
            },
        )
    )
    await session.commit()
    await session.refresh(msg)
    log.info(
        "inbox.message.sent",
        channel=channel,
        lead_id=str(lead_id),
        external_id=external_id,
    )
    return msg


# ---------------------------------------------------------------------------
# Phone — click-to-call (G4)
# ---------------------------------------------------------------------------

async def place_call(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    lead_id: UUID,
    from_extension: str,
    manager_user_id: UUID | None = None,
) -> dict:
    """Click-to-call: ask Mango to bridge the manager's extension with
    the lead's phone. The canonical InboxMessage row arrives back via
    the `call_end` webhook a few minutes later, so this function does
    NOT write to `inbox_messages` — only logs the dispatch and returns
    Mango's response.

    Raises `InboxMessageNotFound` if the lead is missing,
    `InboxMessageBadRequest` if the lead has no phone,
    `InboxSendError` for Mango failures (wraps `MangoCallError`).
    """
    res = await session.execute(
        select(Lead)
        .where(Lead.id == lead_id)
        .where(Lead.workspace_id == workspace_id)
    )
    lead = res.scalar_one_or_none()
    if lead is None:
        raise InboxMessageNotFound(str(lead_id))
    if not lead.phone:
        raise InboxMessageBadRequest("recipient_not_set:phone")

    from app.inbox.adapters.phone import PhoneAdapter

    adapter = PhoneAdapter()
    try:
        result = await adapter.initiate_call(
            from_extension=str(from_extension),
            to_number=str(lead.phone),
        )
    except Exception as exc:  # noqa: BLE001
        raise InboxSendError(str(exc)) from exc

    log.info(
        "inbox.phone.call.initiated",
        lead_id=str(lead_id),
        from_extension=from_extension,
        manager_user_id=str(manager_user_id) if manager_user_id else None,
    )
    return result


# ---------------------------------------------------------------------------
# Merged feed for a single lead
# ---------------------------------------------------------------------------

async def list_for_lead(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    lead_id: UUID,
) -> InboxFeedOut:
    """Return the unified inbox feed for a lead.

    Merges `inbox_items` (Gmail) with `inbox_messages` (tg / max /
    phone), sorted by `created_at` ASC so the UI renders oldest at top.
    """
    lead_row = await session.execute(
        select(
            Lead.email,
            Lead.phone,
            Lead.tg_chat_id,
            Lead.max_user_id,
        )
        .where(Lead.id == lead_id)
        .where(Lead.workspace_id == workspace_id)
    )
    lead_meta = lead_row.first()

    email_rows = await session.execute(
        select(InboxItem)
        .where(InboxItem.workspace_id == workspace_id)
        .where(
            InboxItem.suggested_action.is_not(None)  # placeholder; real link is via Activity
        )
    )
    # NOTE: InboxItem is workspace-scoped; the lead link lives on Activity.
    # G1 returns the InboxMessage stream only — the email side joins
    # through Activity in G5 (Gmail Send), so for now the email leg is
    # empty when we can't trace the link cheaply. The merged-feed shape
    # is correct; G5 fills it in.
    _ = email_rows  # silence unused; placeholder for the join

    msg_rows = await session.execute(
        select(InboxMessage)
        .where(InboxMessage.workspace_id == workspace_id)
        .where(InboxMessage.lead_id == lead_id)
        .order_by(InboxMessage.created_at.asc())
    )
    messages = list(msg_rows.scalars())

    entries: list[InboxFeedEntry] = [
        InboxFeedEntry(
            id=m.id,
            channel=m.channel,
            direction=m.direction,
            body=m.body,
            sender_id=m.sender_id,
            media_url=m.media_url,
            call_duration=m.call_duration,
            call_status=m.call_status,
            transcript=m.transcript,
            summary=m.summary,
            created_at=m.created_at,
        )
        for m in messages
    ]

    links: dict[str, InboxFeedChannelLink] = {
        "email": InboxFeedChannelLink(
            linked=bool(lead_meta and lead_meta.email),
            address=lead_meta.email if lead_meta else None,
        ),
        "telegram": InboxFeedChannelLink(
            linked=bool(lead_meta and lead_meta.tg_chat_id),
            chat_id=lead_meta.tg_chat_id if lead_meta else None,
        ),
        "max": InboxFeedChannelLink(
            linked=bool(lead_meta and lead_meta.max_user_id),
            user_id=lead_meta.max_user_id if lead_meta else None,
        ),
        "phone": InboxFeedChannelLink(
            linked=bool(lead_meta and lead_meta.phone),
            number=lead_meta.phone if lead_meta else None,
        ),
    }
    return InboxFeedOut(messages=entries, channels_linked=links)


# ---------------------------------------------------------------------------
# Unmatched (lead_id IS NULL)
# ---------------------------------------------------------------------------

async def list_unmatched_messages(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[InboxMessage], int]:
    page = max(page, 1)
    page_size = max(min(page_size, 200), 1)
    offset = (page - 1) * page_size

    total_res = await session.execute(
        select(func.count())
        .select_from(InboxMessage)
        .where(InboxMessage.workspace_id == workspace_id)
        .where(InboxMessage.lead_id.is_(None))
    )
    total = int(total_res.scalar_one() or 0)

    rows_res = await session.execute(
        select(InboxMessage)
        .where(InboxMessage.workspace_id == workspace_id)
        .where(InboxMessage.lead_id.is_(None))
        .order_by(InboxMessage.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    return list(rows_res.scalars()), total


# ---------------------------------------------------------------------------
# Assign an unmatched message to a lead
# ---------------------------------------------------------------------------

async def assign(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    message_id: UUID,
    lead_id: UUID,
) -> InboxMessage:
    res = await session.execute(
        select(InboxMessage)
        .where(InboxMessage.id == message_id)
        .where(InboxMessage.workspace_id == workspace_id)
    )
    msg = res.scalar_one_or_none()
    if msg is None:
        raise InboxMessageNotFound(str(message_id))

    lead_res = await session.execute(
        select(Lead.id)
        .where(Lead.id == lead_id)
        .where(Lead.workspace_id == workspace_id)
    )
    if lead_res.scalar_one_or_none() is None:
        raise InboxMessageBadRequest(f"lead {lead_id} not in workspace")

    msg.lead_id = lead_id
    await session.commit()
    await session.refresh(msg)
    return msg
