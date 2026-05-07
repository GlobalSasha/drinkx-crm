"""Email → Lead matching engine.

Given a Gmail message's from + to addresses, find the lead in the
caller's workspace this email belongs to. Confidence escalates from
domain-only (0.7) up to exact contact-email match (1.0).

Threshold for auto-attaching to the lead's Activity feed: 0.8. Below
that, the message is parked in `inbox_items` for human review.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contacts.models import Contact
from app.leads.models import Lead

# Generic mailbox providers — never used for domain matching because
# everyone shares them. Extend as we encounter false positives.
_GENERIC_DOMAINS = frozenset(
    {
        "gmail.com",
        "yandex.ru",
        "yandex.com",
        "ya.ru",
        "mail.ru",
        "outlook.com",
        "hotmail.com",
        "yahoo.com",
        "icloud.com",
        "me.com",
        "googlemail.com",
        "protonmail.com",
        "live.com",
        "msn.com",
        "rambler.ru",
        "list.ru",
        "bk.ru",
        "inbox.ru",
    }
)

CONFIDENCE_THRESHOLD = 0.8


@dataclass
class MatchResult:
    lead_id: UUID | None
    confidence: float
    match_type: str  # 'contact_email' | 'lead_email' | 'domain' | 'none'

    @property
    def auto_attach(self) -> bool:
        return self.lead_id is not None and self.confidence >= CONFIDENCE_THRESHOLD


def _domain_of(addr: str) -> str:
    """Lowercased domain part of an email, '' if malformed."""
    if not addr or "@" not in addr:
        return ""
    return addr.rsplit("@", 1)[1].strip().lower()


async def match_email(
    session: AsyncSession,
    *,
    from_email: str,
    to_emails: list[str],
    workspace_id: UUID,
) -> MatchResult:
    """Resolve an email's from/to addresses to a Lead in this workspace.

    Order:
      1. Contact.email exact match (any of from + to) → 1.0
      2. Lead.email exact match (any of from + to)    → 0.95
      3. Single Lead with `website ILIKE %domain%` for the from-domain → 0.7
         (skipped if the domain is a generic mailbox provider, or if more
         than one lead matches the domain)
      4. None → 0.0
    """
    candidates = [a.lower().strip() for a in [from_email, *to_emails] if a]
    if not candidates:
        return MatchResult(lead_id=None, confidence=0.0, match_type="none")

    # 1. Contact.email
    res = await session.execute(
        select(Contact.lead_id, Lead.workspace_id)
        .join(Lead, Lead.id == Contact.lead_id)
        .where(Contact.email.in_(candidates))
        .where(Lead.workspace_id == workspace_id)
        .limit(1)
    )
    row = res.first()
    if row is not None:
        lead_id, _ = row
        return MatchResult(
            lead_id=lead_id, confidence=1.0, match_type="contact_email"
        )

    # 2. Lead.email
    res = await session.execute(
        select(Lead.id)
        .where(Lead.email.in_(candidates))
        .where(Lead.workspace_id == workspace_id)
        .limit(1)
    )
    lead_id = res.scalar_one_or_none()
    if lead_id is not None:
        return MatchResult(
            lead_id=lead_id, confidence=0.95, match_type="lead_email"
        )

    # 3. Domain match against Lead.website — only if exactly one lead matches
    domain = _domain_of(from_email)
    if domain and domain not in _GENERIC_DOMAINS:
        res = await session.execute(
            select(Lead.id)
            .where(Lead.workspace_id == workspace_id)
            .where(Lead.website.ilike(f"%{domain}%"))
            .limit(2)
        )
        lead_ids = [r[0] for r in res.all()]
        if len(lead_ids) == 1:
            return MatchResult(
                lead_id=lead_ids[0], confidence=0.7, match_type="domain"
            )

    return MatchResult(lead_id=None, confidence=0.0, match_type="none")
