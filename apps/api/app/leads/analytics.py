"""Lead attribution analytics — «какой канал приносит сделки».

Groups a workspace's leads by their resolved UTM source dictionary row and
reports, per source: how many leads it brought, how many were won, and the
revenue (sum of `deal_amount`) of those won deals. Leads with no UTM source
fall into a single `source=None` bucket (direct / unattributed).

Merged-away duplicates are archived (`archived_at` set by the merge), so the
`archived_at IS NULL` filter keeps them from double-counting. Lost leads stay
in the denominator — they came from the channel but didn't convert.
"""
from __future__ import annotations

import uuid

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.leads.models import Lead
from app.utm.models import UtmSource


async def utm_source_stats(db: AsyncSession, workspace_id: uuid.UUID) -> list[dict]:
    """Per-UTM-source rollup for a workspace, ordered by lead count desc."""
    won = Lead.won_at.isnot(None)
    stmt = (
        select(
            UtmSource.name.label("source"),
            func.count(Lead.id).label("leads"),
            func.count(Lead.id).filter(won).label("won"),
            func.coalesce(
                func.sum(case((won, Lead.deal_amount), else_=0)), 0
            ).label("won_sum"),
        )
        .select_from(Lead)
        .outerjoin(UtmSource, UtmSource.id == Lead.utm_source_id)
        .where(Lead.workspace_id == workspace_id, Lead.archived_at.is_(None))
        .group_by(UtmSource.name)
        .order_by(func.count(Lead.id).desc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        {"source": r.source, "leads": r.leads, "won": r.won, "won_sum": r.won_sum}
        for r in rows
    ]
