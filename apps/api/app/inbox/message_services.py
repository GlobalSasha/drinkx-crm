"""Messenger / phone inbox services — Sprint 3.4 G1 skeleton.

This module mediates between channel adapters and the `inbox_messages`
table. The G1 surface:

  * `normalize_phone`            — pure utility for E.164-ish numbers.
  * `match_lead`                 — webhook payload → Lead.id or None.
  * `receive`                    — idempotent upsert from webhook payload.
  * `list_for_lead`              — merged feed (inbox_items + inbox_messages).
  * `list_unmatched_messages`    — InboxMessage rows with lead_id IS NULL.
  * `assign`                     — set inbox_messages.lead_id (PATCH).

Sending lives behind `send` but is stubbed in G1 — the channel-specific
adapters (G2 / G3 / G4) implement the wire calls.
"""
from __future__ import annotations

import re
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

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
    log.info(
        "inbox.message.received",
        channel=payload.channel,
        direction=payload.direction,
        matched=lead_id is not None,
        external_id=payload.external_id,
    )
    return msg, True


# ---------------------------------------------------------------------------
# Send (G1 stub — wired up in G2/G3/G4)
# ---------------------------------------------------------------------------

async def send(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    msg: OutboundMessage,
) -> InboxMessage:
    """Dispatch via the channel adapter, persist as outbound row.

    G1 leaves this as a stub — the adapters and the workspace-level
    credentials lookup land in G2 (Telegram), G3 (MAX), G4 (Phone).
    """
    raise NotImplementedError(
        f"send for channel '{msg.channel}' is wired up in G2/G3/G4"
    )


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
