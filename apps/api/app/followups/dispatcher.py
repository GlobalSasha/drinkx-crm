"""Cron-driven follow-up reminder emitter.

Iterates Followups due within the next 24h that haven't been dispatched
yet. For each: creates an Activity(type='reminder', reminder_trigger_at=
followup.due_at) attached to the same lead, and stamps
followup.dispatched_at = now.

Idempotent: re-running within the same window is a no-op because
dispatched_at is non-null.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.activity.models import Activity, ActivityType
from app.followups.models import Followup
from app.leads.models import Lead

log = structlog.get_logger()

_LOOKAHEAD = timedelta(hours=24)


async def run_followup_dispatch(session: AsyncSession) -> int:
    """Returns the number of activity rows created this tick.

    Sprint 2.6 stability fix: bulk-fetch every lead referenced by the
    due followups in a single `WHERE id IN (...)` SELECT before the
    loop. Pre-fix this was an N+1 (one SELECT per followup), which
    serialized round-trips on the 15-min cron when many followups
    came due at once.
    """
    now = datetime.now(timezone.utc)
    res = await session.execute(
        select(Followup).where(
            Followup.dispatched_at.is_(None),
            Followup.due_at.is_not(None),
            Followup.due_at <= now + _LOOKAHEAD,
            Followup.status.in_(("pending", "active")),
        )
    )
    followups = list(res.scalars().all())

    if not followups:
        return 0

    # One SELECT for all referenced leads. Dedup the lead_id list —
    # multiple followups can target the same lead and we only need
    # one row per id.
    lead_ids = {fu.lead_id for fu in followups}
    leads_res = await session.execute(
        select(
            Lead.id, Lead.assigned_to, Lead.workspace_id, Lead.company_name
        ).where(Lead.id.in_(lead_ids))
    )
    # Map id → tuple(assigned_to, workspace_id, company_name). Missing
    # ids (lead deleted between the followup write and this tick)
    # surface as `None` from `.get(...)` and the per-followup loop
    # logs + skips notification.
    leads_by_id: dict = {
        row[0]: (row[1], row[2], row[3]) for row in leads_res.all()
    }

    # Lazy import to avoid loading the notifications domain when no followups
    # were due (cron tick is hot path).
    from app.notifications.services import safe_notify

    created = 0
    for fu in followups:
        activity = Activity(
            lead_id=fu.lead_id,
            user_id=None,           # system-generated
            type=ActivityType.reminder.value,
            reminder_trigger_at=fu.due_at,
            payload_json={"followup_id": str(fu.id), "name": fu.name},
            body=fu.name,
        )
        session.add(activity)
        fu.dispatched_at = now
        created += 1

        # Notify the lead's current owner (if any). Best-effort — never
        # fail the cron. Lookup the bulk-fetched dict instead of a
        # per-iteration SELECT.
        lead_row = leads_by_id.get(fu.lead_id)
        if lead_row is None:
            # Lead was deleted between followup creation and this
            # tick. Activity still gets staged (FK CASCADE would
            # have removed it on lead-delete; if we're here, the
            # lead exists in some pending-delete state we don't
            # want to crash on). Skip notification — there's no
            # owner to notify.
            log.warning(
                "followup_dispatch.lead_missing",
                followup_id=str(fu.id),
                lead_id=str(fu.lead_id),
            )
            continue
        assigned_to, workspace_id, company_name = lead_row
        if assigned_to is None or workspace_id is None:
            continue

        try:
            await safe_notify(
                session,
                workspace_id=workspace_id,
                user_id=assigned_to,
                kind="followup_due",
                title=f"Напоминание: {fu.name[:120]}",
                body=f"{company_name or '—'} — срок {fu.due_at.strftime('%d.%m %H:%M') if fu.due_at else ''}",
                lead_id=fu.lead_id,
            )
        except Exception as exc:
            log.warning("followup_dispatch.notify_failed", error=str(exc)[:200])

    await session.commit()
    return created
