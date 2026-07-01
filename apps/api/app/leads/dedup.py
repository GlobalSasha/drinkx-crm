"""Lead duplicate detection — Odoo `_compute_potential_lead_duplicates` pattern.

Non-destructive: surfaces likely duplicates of a lead so a manager can decide
to merge them (the merge itself is a separate, human-triggered action). Matches
on three OR-combined keys, all derived/normalized:

  • email_domain_criterion  — same corporate email domain (free-mail excluded)
  • phone_e164              — same E.164 phone
  • company_id              — same linked company

A "duplicate bomb" guard mirrors Odoo's SEARCH_RESULT_LIMIT: if a key matches a
whole crowd (≥ limit rows), it is not a useful signal, so we suppress rather
than flood the manager with false positives. Archived and trashed (soft-deleted) leads are
excluded — we only suggest merging into live leads.
"""
from __future__ import annotations

import uuid

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
            Lead.deleted_at.is_(None),
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


# ── merge ──────────────────────────────────────────────────────────
# Scalar lead fields filled onto the master from duplicates when the master's
# own value is empty (first non-empty wins). Setting email/phone re-derives the
# normalized dedup keys via the model @validates hooks.
_MERGE_FILL_FIELDS = (
    "email", "phone", "website", "inn", "city", "segment",
    "deal_type", "deal_amount", "deal_quantity", "deal_equipment",
    "next_step", "blocker",
)


class MergeError(Exception):
    """Raised when a merge request is invalid (no master / no valid duplicates)."""


async def merge_leads(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    master_id: uuid.UUID,
    duplicate_ids: list[uuid.UUID],
    user_id: uuid.UUID | None = None,
) -> Lead:
    """Merge duplicate leads into `master_id` — Odoo `_merge_opportunity` pattern.

    Soft + reversible: history (activities, contacts, follow-ups) is re-pointed
    to the master; the master's empty scalar fields are filled from the dups;
    tags are unioned; each duplicate is archived with `merged_into_id` set (not
    deleted). Human-triggered — the caller picks the master.
    """
    from datetime import datetime, timezone

    from sqlalchemy import update

    from app.activity.models import Activity
    from app.contacts.models import Contact
    from app.followups.models import Followup

    master = (
        await db.execute(
            select(Lead).where(Lead.id == master_id, Lead.workspace_id == workspace_id)
        )
    ).scalar_one_or_none()
    if master is None:
        raise MergeError("master lead not found in workspace")
    if master.deleted_at is not None:
        raise MergeError("master lead is in trash — restore it before merging")

    wanted = [d for d in duplicate_ids if d != master_id]
    dups = list(
        (
            await db.execute(
                select(Lead).where(
                    Lead.id.in_(wanted),
                    Lead.workspace_id == workspace_id,
                    Lead.merged_into_id.is_(None),
                    Lead.deleted_at.is_(None),
                )
            )
        ).scalars().all()
    )
    if not dups:
        raise MergeError("no valid duplicates to merge")

    real_dup_ids = [d.id for d in dups]

    # 1. Fill empty master scalar fields from the duplicates (first non-empty).
    for field in _MERGE_FILL_FIELDS:
        if getattr(master, field, None):
            continue
        for d in dups:
            val = getattr(d, field, None)
            if val:
                setattr(master, field, val)
                break

    # 2. Union tags.
    merged_tags = list(master.tags_json or [])
    for d in dups:
        for tag in d.tags_json or []:
            if tag not in merged_tags:
                merged_tags.append(tag)
    master.tags_json = merged_tags

    # 3. Re-point user-visible history to the master.
    for model in (Activity, Contact, Followup):
        await db.execute(
            update(model).where(model.lead_id.in_(real_dup_ids)).values(lead_id=master_id)
        )

    # 4. Archive the duplicates, pointing them at the survivor (reversible).
    now = datetime.now(timezone.utc)
    for d in dups:
        d.archived_at = now
        d.merged_into_id = master_id

    # 5. Audit trail on the master.
    db.add(
        Activity(
            lead_id=master_id,
            user_id=user_id,
            type="system",
            body=f"Объединены дубли: {len(dups)} лид(ов) → этот лид",
            payload_json={"merged_lead_ids": [str(i) for i in real_dup_ids]},
        )
    )

    await db.flush()
    return master
