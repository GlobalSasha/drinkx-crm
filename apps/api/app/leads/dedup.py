"""Lead duplicate detection — Odoo `_compute_potential_lead_duplicates` pattern.

Non-destructive: surfaces likely duplicates of a lead so a manager can decide
to merge them (the merge itself is a separate, human-triggered action). Matches
on three OR-combined keys, all derived/normalized:

  • email_domain_criterion  — same corporate email domain (free-mail excluded)
  • phone_e164              — same E.164 phone
  • company_id              — same linked company

A "duplicate bomb" guard mirrors Odoo's SEARCH_RESULT_LIMIT: if a key matches a
whole crowd (≥ limit rows), it is not a useful signal, so we suppress rather
than flood the manager with false positives. Archived leads are excluded — we
only suggest merging into live leads.
"""
from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.leads.models import Lead

# Odoo SEARCH_RESULT_LIMIT.
DUP_LIMIT = 21


async def find_duplicates(db: AsyncSession, lead: Lead, *, limit: int = DUP_LIMIT) -> list[Lead]:
    """Return live leads in the same workspace that look like duplicates of `lead`."""
    keys = []
    if lead.email_domain_criterion:
        keys.append(Lead.email_domain_criterion == lead.email_domain_criterion)
    if lead.phone_e164:
        keys.append(Lead.phone_e164 == lead.phone_e164)
    if lead.company_id:
        keys.append(Lead.company_id == lead.company_id)
    if not keys:
        return []

    stmt = (
        select(Lead)
        .where(
            Lead.workspace_id == lead.workspace_id,
            Lead.id != lead.id,
            Lead.archived_at.is_(None),
            or_(*keys),
        )
        .order_by(Lead.created_at.asc())
        .limit(limit)
    )
    rows = list((await db.execute(stmt)).scalars().all())
    # Dupe-bomb guard: a key that matches the whole crowd is noise, not a match.
    if len(rows) >= limit:
        return []
    return rows
