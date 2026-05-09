"""Per-message processing — parse Gmail dict → match → store.

Called by `app.inbox.sync` for every Gmail message we pull (history
backfill + every-5-min incremental tick).

Behaviour:
- Dedup against `activities.gmail_message_id` AND `inbox_items.gmail_message_id`.
- Match via `matcher.match_email`. Confidence ≥ 0.8 → write an Activity row
  attached to the matched lead. Lower confidence (or no match) → write an
  InboxItem for human review and queue an AI suggestion task.
- Per-message try/except: ANY failure returns False without raising.

ADR-019: Activity.user_id records the channel's owner (audit trail).
The lead-card feed never filters by user_id; emails are always lead-scoped.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.activity.models import Activity
from app.config import get_settings
from app.inbox.email_parser import (
    extract_body,
    headers_to_dict,
    is_sent_message,
    parse_email_address,
    parse_email_list,
    parse_rfc2822,
)
from app.inbox.matcher import CONFIDENCE_THRESHOLD, match_email
from app.inbox.models import InboxItem

log = structlog.get_logger()

# Skip storing raw payload if it would bloat the row past 50KB.
MAX_RAW_PAYLOAD_BYTES = 50_000


async def _already_processed(
    session: AsyncSession, *, gmail_message_id: str
) -> bool:
    """True if either an Activity or InboxItem already references this id."""
    res = await session.execute(
        select(Activity.id)
        .where(Activity.gmail_message_id == gmail_message_id)
        .limit(1)
    )
    if res.scalar_one_or_none() is not None:
        return True
    res = await session.execute(
        select(InboxItem.id)
        .where(InboxItem.gmail_message_id == gmail_message_id)
        .limit(1)
    )
    return res.scalar_one_or_none() is not None


def _maybe_raw_payload(raw_message: dict[str, Any]) -> dict[str, Any] | None:
    """Return the payload if it serialises under MAX_RAW_PAYLOAD_BYTES, else None."""
    try:
        encoded = json.dumps(raw_message, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return None
    if len(encoded.encode("utf-8")) > MAX_RAW_PAYLOAD_BYTES:
        return None
    return raw_message


async def process_message(
    session: AsyncSession,
    *,
    raw_message: dict[str, Any],
    user_id: UUID | None,
    workspace_id: UUID,
) -> bool:
    """Parse → dedup → match → store. Never raises."""
    bound_log = log.bind(
        workspace_id=str(workspace_id),
        user_id=str(user_id) if user_id else None,
        gmail_id=raw_message.get("id") if isinstance(raw_message, dict) else None,
    )
    try:
        gmail_message_id = (raw_message or {}).get("id")
        if not gmail_message_id or not isinstance(gmail_message_id, str):
            bound_log.warning("inbox.process_message.missing_id")
            return False

        if await _already_processed(session, gmail_message_id=gmail_message_id):
            return False

        s = get_settings()
        headers = headers_to_dict(raw_message)
        from_email = parse_email_address(headers.get("from", ""))
        to_emails = parse_email_list(headers.get("to", ""))
        subject = (headers.get("subject") or "")[:500]
        received_at = parse_rfc2822(headers.get("date", "")) or datetime.now(
            tz=timezone.utc
        )
        body_full = extract_body(raw_message)
        body = body_full[: s.gmail_max_body_chars] if body_full else ""
        direction = "outbound" if is_sent_message(raw_message) else "inbound"
        raw_payload = _maybe_raw_payload(raw_message)

        match = await match_email(
            session,
            from_email=from_email,
            to_emails=to_emails,
            workspace_id=workspace_id,
        )

        if match.auto_attach and match.lead_id is not None:
            activity = Activity(
                lead_id=match.lead_id,
                user_id=user_id,
                type="email",
                channel="gmail",
                direction=direction,
                subject=subject or None,
                body=body or None,
                gmail_message_id=gmail_message_id,
                gmail_raw_json=raw_payload,
                from_identifier=from_email or None,
                to_identifier=(",".join(to_emails))[:300] if to_emails else None,
                payload_json={
                    "match_type": match.match_type,
                    "match_confidence": match.confidence,
                    "received_at": received_at.isoformat(),
                },
            )
            session.add(activity)

            # Sprint 2.5 G1: fan out to the Automation Builder. The
            # action handlers stage Activity rows (commits atomically
            # with the email attach below) AND queue any email
            # dispatches into a contextvar list — Sprint 2.6 G1
            # stability fix moved SMTP outside this transaction so a
            # slow / failing SMTP can't hold the DB connection.
            from app.automation_builder.dispatch import (
                collect_pending_email_dispatches,
                flush_pending_email_dispatches,
            )
            from app.automation_builder.services import safe_evaluate_trigger
            from app.leads.models import Lead

            lead_res = await session.execute(
                select(Lead).where(Lead.id == match.lead_id)
            )
            matched_lead = lead_res.scalar_one_or_none()

            async with collect_pending_email_dispatches() as pending:
                if matched_lead is not None:
                    await safe_evaluate_trigger(
                        session,
                        workspace_id=workspace_id,
                        trigger="inbox_match",
                        lead=matched_lead,
                        payload={
                            "match_type": match.match_type,
                            "direction": direction,
                        },
                    )

                await session.commit()
                bound_log.info(
                    "inbox.process_message.attached_to_lead",
                    lead_id=str(match.lead_id),
                    match_type=match.match_type,
                    confidence=match.confidence,
                )

            # Drain queued email dispatches AFTER commit. Opens a new
            # session internally; never raises (a dispatch failure
            # only updates the matching Activity to status='failed').
            await flush_pending_email_dispatches(pending)
            return True

        # Below-threshold or no match → park for human review.
        item = InboxItem(
            workspace_id=workspace_id,
            user_id=user_id,
            gmail_message_id=gmail_message_id,
            from_email=from_email or "",
            to_emails=to_emails,
            subject=subject or None,
            body_preview=(body[:500] if body else None),
            received_at=received_at,
            direction=direction,
            status="pending",
        )
        session.add(item)
        await session.commit()
        await session.refresh(item)

        try:
            from app.scheduled.celery_app import celery_app

            celery_app.send_task(
                "app.scheduled.jobs.generate_inbox_suggestion",
                args=[str(item.id)],
            )
        except Exception as exc:
            bound_log.warning(
                "inbox.suggestion_dispatch_failed",
                inbox_item_id=str(item.id),
                error=str(exc)[:200],
            )

        bound_log.info(
            "inbox.process_message.parked_pending",
            inbox_item_id=str(item.id),
            match_type=match.match_type,
        )
        return True

    except Exception as exc:
        bound_log.exception(
            "inbox.process_message.failed", error=str(exc)[:200]
        )
        try:
            await session.rollback()
        except Exception:
            pass
        return False


__all__ = ["process_message", "CONFIDENCE_THRESHOLD"]
