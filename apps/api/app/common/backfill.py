"""One-off backfill of the normalized dedup keys.

Existing `leads` / `contacts` rows created before the normalization @validates
hooks landed have NULL `phone_e164` / `email_normalized` /
`email_domain_criterion` — they only fill on the next save. This re-derives
them in bulk via the same helpers the live save-path uses, so duplicate
detection and channel analytics see historical rows too.

Idempotent: only rows still missing a key are selected, and re-deriving a key
that is already correct is a no-op. Commits per batch so a large workspace
doesn't hold one giant transaction. Wired to a manual-trigger Celery task
(`app.scheduled.jobs.backfill_normalized_keys`).
"""
from __future__ import annotations

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.email import email_domain_criterion, normalize_email
from app.common.phone import to_e164
from app.contacts.models import Contact
from app.leads.models import Lead

DEFAULT_BATCH = 500


async def backfill_normalized_keys(db: AsyncSession, *, batch_size: int = DEFAULT_BATCH) -> int:
    """Re-derive normalized keys on leads + contacts. Returns rows touched.

    Compatible with the scheduled `_run(session)` wrapper (single positional
    session arg) — the wrapper records the return value as `affected_count`.
    """
    # Loading candidates once and mutating across batch commits requires the
    # async session to NOT expire the still-pending objects on commit (an
    # expired attribute access would trigger illegal lazy IO).
    sync_session = db.sync_session
    prev_expire = sync_session.expire_on_commit
    sync_session.expire_on_commit = False
    try:
        touched = 0
        touched += await _backfill_leads(db, batch_size)
        touched += await _backfill_contacts(db, batch_size)
        return touched
    finally:
        sync_session.expire_on_commit = prev_expire


async def _backfill_leads(db: AsyncSession, batch_size: int) -> int:
    stmt = select(Lead).where(
        or_(
            and_(Lead.email.isnot(None), Lead.email_normalized.is_(None)),
            and_(Lead.phone.isnot(None), Lead.phone_e164.is_(None)),
        )
    )
    rows = (await db.execute(stmt)).scalars().all()
    for i, lead in enumerate(rows, start=1):
        if lead.email and lead.email_normalized is None:
            norm = normalize_email(lead.email)
            lead.email_normalized = norm
            lead.email_domain_criterion = email_domain_criterion(norm)
        if lead.phone and lead.phone_e164 is None:
            lead.phone_e164 = to_e164(lead.phone)
        if i % batch_size == 0:
            await db.commit()
    await db.commit()
    return len(rows)


async def _backfill_contacts(db: AsyncSession, batch_size: int) -> int:
    stmt = select(Contact).where(
        or_(
            and_(Contact.email.isnot(None), Contact.email_normalized.is_(None)),
            and_(Contact.phone.isnot(None), Contact.phone_e164.is_(None)),
        )
    )
    rows = (await db.execute(stmt)).scalars().all()
    for i, contact in enumerate(rows, start=1):
        if contact.email and contact.email_normalized is None:
            contact.email_normalized = normalize_email(contact.email)
        if contact.phone and contact.phone_e164 is None:
            contact.phone_e164 = to_e164(contact.phone)
        if i % batch_size == 0:
            await db.commit()
    await db.commit()
    return len(rows)
