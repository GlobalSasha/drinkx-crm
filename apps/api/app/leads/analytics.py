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

from sqlalchemy import case, func, select, text
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


# ── stage-dwell analytics ──────────────────────────────────────────
# «Где застревают сделки» — per active stage: how long leads sit in it and
# how many are stuck there right now. Reads the append-only lead_stage_history
# (migration 0029); completed rows (exited_at set) carry duration_sec, open
# rows (exited_at NULL) are the leads currently in the stage.
#
# The "stuck" threshold is each stage's own rot_days (fallback 14d) — the same
# rotting config the pipeline already uses, not a flat number. Terminal
# (won/lost) stages are excluded; dwell time there is meaningless. Workspace
# scope comes through the stage's pipeline. Median/p90 use percentile_cont
# (core Postgres). Returns seconds; the caller converts to days.
_STAGE_DWELL_SQL = text(
    """
    WITH completed AS (
        SELECT lsh.stage_id, lsh.duration_sec
        FROM lead_stage_history lsh
        JOIN leads l ON l.id = lsh.lead_id
        WHERE l.workspace_id = :wid
          AND lsh.exited_at IS NOT NULL
          AND lsh.duration_sec IS NOT NULL
    ),
    agg AS (
        SELECT stage_id,
               count(*) AS completed_count,
               avg(duration_sec) AS avg_sec,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY duration_sec) AS median_sec,
               percentile_cont(0.9) WITHIN GROUP (ORDER BY duration_sec) AS p90_sec
        FROM completed
        GROUP BY stage_id
    ),
    stuck AS (
        SELECT lsh.stage_id, count(*) AS cnt
        FROM lead_stage_history lsh
        JOIN leads l ON l.id = lsh.lead_id
        JOIN stages s ON s.id = lsh.stage_id
        WHERE l.workspace_id = :wid
          AND lsh.exited_at IS NULL
          AND l.archived_at IS NULL
          AND EXTRACT(EPOCH FROM (now() - lsh.entered_at))
              > GREATEST(COALESCE(s.rot_days, 0), 14) * 86400
        GROUP BY lsh.stage_id
    )
    SELECT s.id::text AS stage_id, s.name AS stage_name, s.position,
           COALESCE(a.completed_count, 0) AS completed_count,
           a.avg_sec, a.median_sec, a.p90_sec,
           COALESCE(st.cnt, 0) AS stuck_count
    FROM stages s
    JOIN pipelines p ON p.id = s.pipeline_id
    LEFT JOIN agg a ON a.stage_id = s.id
    LEFT JOIN stuck st ON st.stage_id = s.id
    WHERE p.workspace_id = :wid AND s.is_won = false AND s.is_lost = false
    ORDER BY a.median_sec DESC NULLS LAST, s.position
    """
)


def _to_days(sec) -> float | None:
    return round(sec / 86400, 1) if sec is not None else None


async def stage_dwell_summary(db: AsyncSession, workspace_id: uuid.UUID) -> list[dict]:
    """Per active stage: completed-visit count, avg/median/p90 dwell (days) and
    how many leads are stuck past the stage's rot_days. Bottlenecks first."""
    rows = (await db.execute(_STAGE_DWELL_SQL, {"wid": str(workspace_id)})).mappings().all()
    return [
        {
            "stage_id": r["stage_id"],
            "stage_name": r["stage_name"],
            "position": r["position"],
            "completed_count": r["completed_count"],
            "avg_days": _to_days(r["avg_sec"]),
            "median_days": _to_days(r["median_sec"]),
            "p90_days": _to_days(r["p90_sec"]),
            "stuck_count": r["stuck_count"],
        }
        for r in rows
    ]
