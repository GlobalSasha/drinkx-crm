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
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal
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
from app.inbox.matcher import match_email
from app.inbox.models import InboxItem

log = structlog.get_logger()

# Skip storing raw payload if it would bloat the row past 50KB.
MAX_RAW_PAYLOAD_BYTES = 50_000


# ---------------------------------------------------------------------------
# Routing — pure decision layer applied before any DB writes.
# ---------------------------------------------------------------------------

EmailRoute = Literal["attach_to_lead", "inbox", "ignore"]


@dataclass(frozen=True)
class RoutingDecision:
    route: EmailRoute
    reason: str


# Senders that are almost always automated (newsletter / notification /
# bounce). Matched as a case-insensitive prefix on the local-part.
_NOREPLY_PREFIXES: tuple[str, ...] = (
    "noreply@",
    "no-reply@",
    "donotreply@",
    "newsletter@",
    "mailer-daemon@",
    "postmaster@",
)

# Substrings that, if present in subject or body preview, mark the message
# as bulk/marketing. Case-insensitive match.
_UNSUB_KEYWORDS: tuple[str, ...] = (
    "unsubscribe",
    "отписаться",
    "рассылка",
    "you are receiving this",
)

# Mailbox providers used by individuals. A sender on one of these domains
# only goes to the inbox if the subject/body mentions a Drinkx-related
# keyword — otherwise silent ignore.
_PERSONAL_DOMAINS: frozenset[str] = frozenset(
    {
        "gmail.com",
        "mail.ru",
        "yandex.ru",
        "yahoo.com",
        "outlook.com",
        "hotmail.com",
        "icloud.com",
        "bk.ru",
        "list.ru",
        "inbox.ru",
    }
)

# Topical keywords that suggest a personal-mailbox message is a real
# inquiry rather than personal correspondence. Case-insensitive substring.
_KEYWORDS: tuple[str, ...] = (
    "drinkx",
    "дринкикс",
    "дринкх",
    "станция",
    "кофе станция",
    "автомат",
    "концентрат",
    "экстракт",
    "напиток",
    "пилот",
    "установка",
    "коммерческое",
    "сотрудничество",
    "прайс",
    "стоимость",
    "продажа",
)


def _domain_of(email: str) -> str:
    if not email or "@" not in email:
        return ""
    return email.rsplit("@", 1)[1].strip().lower()


def _haystack(subject: str | None, body_preview: str | None) -> str:
    return " ".join(s for s in (subject, body_preview) if s).lower()


def route_email(
    *,
    from_email: str,
    subject: str | None,
    body_preview: str | None,
    has_known_company: bool,
    has_known_contact: bool,
) -> RoutingDecision:
    """Decide where this email goes before any DB writes.

    Pure function — no side effects, no I/O. The caller resolves
    `has_known_company` (workspace's companies.domain) and
    `has_known_contact` (workspace's contacts.email) and applies the
    returned decision afterwards.

    Priority (first match wins):
      1. Sender prefix in `_NOREPLY_PREFIXES`              → ignore
      2. Subject/body contains an unsubscribe keyword      → ignore
      3. Known company-domain OR known contact-email       → attach
      4. Personal mailbox provider + topical keyword       → inbox
      5. Unknown corporate domain                          → inbox
      6. Personal mailbox provider, no topical keyword     → ignore
    """
    sender = (from_email or "").strip().lower()

    if any(sender.startswith(p) for p in _NOREPLY_PREFIXES):
        return RoutingDecision("ignore", "noreply_sender")

    text = _haystack(subject, body_preview)
    if any(k in text for k in _UNSUB_KEYWORDS):
        return RoutingDecision("ignore", "unsubscribe_keyword")

    if has_known_contact:
        return RoutingDecision("attach_to_lead", "known_contact")
    if has_known_company:
        return RoutingDecision("attach_to_lead", "known_company")

    domain = _domain_of(sender)
    if domain in _PERSONAL_DOMAINS:
        if any(k in text for k in _KEYWORDS):
            return RoutingDecision("inbox", "personal_domain_keyword")
        return RoutingDecision("ignore", "personal_no_keyword")

    return RoutingDecision("inbox", "unknown_corporate_domain")


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


# ---------------------------------------------------------------------------
# DB lookups for routing inputs + Contact auto-creation on attach.
# ---------------------------------------------------------------------------


async def _company_domain_match(
    session: AsyncSession, *, domain: str, workspace_id: UUID
) -> bool:
    """True iff a company in this workspace has this exact `domain`."""
    if not domain:
        return False
    from app.companies.models import Company

    res = await session.execute(
        select(Company.id)
        .where(Company.workspace_id == workspace_id, Company.domain == domain)
        .limit(1)
    )
    return res.scalar_one_or_none() is not None


async def _contact_email_match(
    session: AsyncSession, *, email: str, workspace_id: UUID
) -> bool:
    """True iff any Contact in this workspace has this email."""
    if not email:
        return False
    from app.contacts.models import Contact

    res = await session.execute(
        select(Contact.id)
        .where(
            Contact.workspace_id == workspace_id,
            Contact.email == email.lower(),
        )
        .limit(1)
    )
    return res.scalar_one_or_none() is not None


async def _find_company_lead(
    session: AsyncSession, *, domain: str, workspace_id: UUID
) -> tuple[UUID | None, UUID | None]:
    """Resolve a sender domain → (company_id, lead_id).

    `lead_id` is only set when the company has exactly one linked lead;
    ambiguous companies (multiple leads) return (company_id, None) so the
    caller can fall back to InboxItem and let a human triage.
    """
    if not domain:
        return None, None
    from app.companies.models import Company
    from app.leads.models import Lead

    res = await session.execute(
        select(Company.id)
        .where(Company.workspace_id == workspace_id, Company.domain == domain)
        .limit(1)
    )
    company_id = res.scalar_one_or_none()
    if company_id is None:
        return None, None

    res = await session.execute(
        select(Lead.id)
        .where(Lead.company_id == company_id, Lead.workspace_id == workspace_id)
        .limit(2)
    )
    lead_rows = [r[0] for r in res.all()]
    return company_id, (lead_rows[0] if len(lead_rows) == 1 else None)


async def _ensure_contact_for_email(
    session: AsyncSession,
    *,
    email: str,
    lead_id: UUID,
    workspace_id: UUID,
    company_id: UUID | None,
) -> None:
    """Insert a nameless Contact for `email` on `lead_id` if none exists.

    Idempotent: skips when a Contact with this email already lives on
    the lead. `name=""` is intentional — the lead-card UI renders it as
    «Неизвестный контакт» with the «уточнить» badge so the manager
    knows to fill it in.
    """
    if not email:
        return
    from app.contacts.models import Contact

    normalized = email.lower()
    res = await session.execute(
        select(Contact.id)
        .where(Contact.lead_id == lead_id, Contact.email == normalized)
        .limit(1)
    )
    if res.scalar_one_or_none() is not None:
        return
    session.add(
        Contact(
            lead_id=lead_id,
            workspace_id=workspace_id,
            company_id=company_id,
            name="",
            email=normalized,
            source="gmail",
            verified_status="to_verify",
            confidence="low",
        )
    )


async def process_message(
    session: AsyncSession,
    *,
    raw_message: dict[str, Any],
    user_id: UUID | None,
    workspace_id: UUID,
) -> bool:
    """Parse → dedup → route → store. Never raises.

    Flow:
      1. Parse Gmail dict into headers + body.
      2. `route_email` returns one of {ignore, attach_to_lead, inbox}.
      3. ignore → debug log, no DB writes.
         attach_to_lead → run `match_email` for the precise lead; fall
           back to the company's single linked lead if the matcher comes
           up empty. Write Activity, ensure a Contact row exists for the
           sender, fan out automations + lead-agent refresh.
         inbox → write InboxItem and queue an AI suggestion task.
    """
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
        body_preview = body[:500] if body else None

        # ---- Routing decision -------------------------------------------------
        sender_domain = _domain_of(from_email)
        has_known_company = await _company_domain_match(
            session, domain=sender_domain, workspace_id=workspace_id
        )
        has_known_contact = await _contact_email_match(
            session, email=from_email, workspace_id=workspace_id
        )
        decision = route_email(
            from_email=from_email,
            subject=subject,
            body_preview=body_preview,
            has_known_company=has_known_company,
            has_known_contact=has_known_contact,
        )

        if decision.route == "ignore":
            bound_log.debug(
                "inbox.process_message.ignored",
                domain=sender_domain,
                reason=decision.reason,
            )
            return True

        # ---- attach_to_lead --------------------------------------------------
        if decision.route == "attach_to_lead":
            match = await match_email(
                session,
                from_email=from_email,
                to_emails=to_emails,
                workspace_id=workspace_id,
            )
            target_lead_id: UUID | None = (
                match.lead_id if match.auto_attach else None
            )
            target_company_id: UUID | None = None
            if target_lead_id is None:
                target_company_id, target_lead_id = await _find_company_lead(
                    session, domain=sender_domain, workspace_id=workspace_id
                )

            if target_lead_id is not None:
                activity = Activity(
                    lead_id=target_lead_id,
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
                        "route": decision.route,
                        "route_reason": decision.reason,
                        "match_type": match.match_type,
                        "match_confidence": match.confidence,
                        "received_at": received_at.isoformat(),
                    },
                )
                session.add(activity)

                # Auto-create a placeholder Contact when the matcher didn't
                # already identify one — fills the lead-card "ЛПР" list
                # with the sender's email so the manager can rename later.
                if match.match_type != "contact_email":
                    await _ensure_contact_for_email(
                        session,
                        email=from_email,
                        lead_id=target_lead_id,
                        workspace_id=workspace_id,
                        company_id=target_company_id,
                    )

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
                    select(Lead).where(Lead.id == target_lead_id)
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
                        lead_id=str(target_lead_id),
                        match_type=match.match_type,
                        confidence=match.confidence,
                        route_reason=decision.reason,
                    )

                # Drain queued email dispatches AFTER commit. Opens a new
                # session internally; never raises (a dispatch failure
                # only updates the matching Activity to status='failed').
                await flush_pending_email_dispatches(pending)

                # Sprint 3.1 Phase E — kick the Lead AI Agent to recompute
                # its banner suggestion 15 min after a NEW inbound email
                # lands on the lead. The 15-min delay is the spec's
                # «менеджер может ответить сам» window — if the manager
                # already replied by the time the worker fires, the
                # refresh just produces a fresh suggestion that reflects
                # the updated activity timeline. Outbound messages don't
                # trigger — those are the manager's own actions.
                if direction == "inbound":
                    try:
                        from app.scheduled.jobs import lead_agent_refresh_suggestion

                        lead_agent_refresh_suggestion.apply_async(
                            args=[str(target_lead_id)],
                            countdown=900,
                        )
                    except Exception as exc:  # noqa: BLE001 — broker hiccup
                        bound_log.warning(
                            "inbox.process_message.lead_agent_refresh_enqueue_failed",
                            lead_id=str(target_lead_id),
                            error=str(exc)[:200],
                        )

                return True

            # Routing said "attach" but neither the matcher nor a unique
            # company link gave us a target lead (e.g. company has 2+
            # leads, ambiguous). Fall through to the inbox path so the
            # message reaches a human triage queue instead of vanishing.
            bound_log.warning(
                "inbox.process_message.attach_no_lead",
                domain=sender_domain,
                reason=decision.reason,
            )

        # ---- inbox (or attach-fallback) --------------------------------------
        item = InboxItem(
            workspace_id=workspace_id,
            user_id=user_id,
            gmail_message_id=gmail_message_id,
            from_email=from_email or "",
            to_emails=to_emails,
            subject=subject or None,
            body_preview=body_preview,
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
            route_reason=decision.reason,
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


__all__ = ["process_message", "route_email", "RoutingDecision"]
