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

from sqlalchemy import and_, case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.leads.models import Lead
from app.utm.models import UtmSource


async def utm_source_stats(db: AsyncSession, workspace_id: uuid.UUID) -> list[dict]:
    """Per-UTM-source rollup for a workspace, ordered by lead count desc."""
    won = Lead.won_at.isnot(None)
    # Plan 025: `deal_amount` is a one-off total for a sale but a MONTHLY fee
    # for a rental — never sum them into one number. `won_sum` is sale-only
    # (one-off) revenue; `won_rental_mrr` is the monthly recurring figure.
    won_sale = and_(won, Lead.commercial_model.is_distinct_from("rental"))
    won_rental = and_(won, Lead.commercial_model == "rental")
    stmt = (
        select(
            UtmSource.name.label("source"),
            func.count(Lead.id).label("leads"),
            func.count(Lead.id).filter(won).label("won"),
            func.coalesce(
                func.sum(case((won_sale, Lead.deal_amount), else_=0)), 0
            ).label("won_sum"),
            func.coalesce(
                func.sum(case((won_rental, Lead.deal_amount), else_=0)), 0
            ).label("won_rental_mrr"),
        )
        .select_from(Lead)
        .outerjoin(UtmSource, UtmSource.id == Lead.utm_source_id)
        .where(Lead.workspace_id == workspace_id, Lead.archived_at.is_(None))
        .group_by(UtmSource.name)
        .order_by(func.count(Lead.id).desc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        {
            "source": r.source,
            "leads": r.leads,
            "won": r.won,
            "won_sum": r.won_sum,
            "won_rental_mrr": r.won_rental_mrr,
        }
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


# ── forecast aggregate (FORECAST-01) ───────────────────────────────
# «Прогноз» раньше считался в браузере по одной странице `GET /leads`
# (`page_size: 500` при потолке роута 200 — то есть 422 и нули вместо сумм).
# Здесь та же формула, но в базе и по всей доступной выборке: страница
# получает готовые числа и не зависит от того, сколько строк поместилось в
# ответ.
#
# Формула воспроизведена дословно, вместе с её известными особенностями —
# менять смысл метрик эта правка не должна:
#   * `deal_amount` продажи и ежемесячная аренда складываются в одно число
#     (`commercial_model` не разделяется, в отличие от utm-статистики);
#   * `archived_at`-дубликаты после слияния не исключаются;
#   * «закрыто за 90 дней» считается по `last_activity_at`, а не по `won_at`;
#   * лид без стадии не попадает ни в одну сумму.
# Единственное отличие от браузерной версии — «под угрозой» наконец работает:
# дни на стадии считаются здесь, по открытой строке `lead_stage_history`
# (в списке лидов `current_stage_days` не заполнялся вовсе, и метрика была
# структурно нулевой).
_FORECAST_SCOPED_CTE = """
    WITH scoped AS (
        SELECT l.id,
               l.company_name,
               l.stage_id,
               l.last_activity_at,
               COALESCE(l.deal_amount, 0) AS amount,
               GREATEST(
                   0,
                   FLOOR(
                       EXTRACT(EPOCH FROM (now() - COALESCE(h.entered_at, l.created_at)))
                       / 86400
                   )
               ) AS stage_days
        FROM leads l
        LEFT JOIN LATERAL (
            SELECT lsh.entered_at
            FROM lead_stage_history lsh
            WHERE lsh.lead_id = l.id
              AND lsh.stage_id = l.stage_id
              AND lsh.exited_at IS NULL
            ORDER BY lsh.entered_at DESC
            LIMIT 1
        ) h ON true
        WHERE l.workspace_id = :wid
          AND l.assignment_status = 'assigned'
          AND l.deleted_at IS NULL
          AND (CAST(:assigned_to AS uuid) IS NULL OR l.assigned_to = CAST(:assigned_to AS uuid))
    )
"""

_FORECAST_BY_STAGE_SQL = text(
    _FORECAST_SCOPED_CTE
    + """
    SELECT s.id::text AS stage_id,
           s.name AS stage_name,
           s.position,
           s.probability,
           s.is_won,
           s.is_lost,
           count(sc.id) AS lead_count,
           COALESCE(sum(sc.amount), 0) AS total,
           COALESCE(sum(sc.amount) FILTER (
               WHERE s.rot_days > 0 AND sc.stage_days > s.rot_days AND sc.amount > 0
           ), 0) AS at_risk_total,
           COALESCE(sum(sc.amount) FILTER (
               WHERE sc.last_activity_at >= now() - interval '90 days'
           ), 0) AS won_recent
    FROM stages s
    JOIN pipelines p ON p.id = s.pipeline_id
    LEFT JOIN scoped sc ON sc.stage_id = s.id
    WHERE p.workspace_id = :wid
    GROUP BY s.id, s.name, s.position, s.probability, s.is_won, s.is_lost
    ORDER BY s.position
    """
)

_FORECAST_AT_RISK_SQL = text(
    _FORECAST_SCOPED_CTE
    + """
    SELECT sc.id::text AS id,
           sc.company_name,
           sc.amount,
           (sc.stage_days - s.rot_days)::int AS overdue_days,
           s.name AS stage_name
    FROM scoped sc
    JOIN stages s ON s.id = sc.stage_id
    JOIN pipelines p ON p.id = s.pipeline_id
    WHERE p.workspace_id = :wid
      AND s.is_won = false
      AND s.is_lost = false
      AND s.rot_days > 0
      AND sc.stage_days > s.rot_days
      AND sc.amount > 0
    ORDER BY sc.amount DESC
    LIMIT :limit
    """
)

AT_RISK_LIMIT = 10


async def forecast_summary(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    *,
    assigned_to: uuid.UUID | None = None,
) -> dict:
    """Суммы прогноза по всей выборке: воронка, взвешенный прогноз, риски,
    закрытые за 90 дней и разбивка по этапам.

    `assigned_to` — сужение до одного человека (менеджер видит только свои
    сделки); `None` — весь workspace.
    """
    params = {"wid": str(workspace_id), "assigned_to": str(assigned_to) if assigned_to else None}
    rows = (await db.execute(_FORECAST_BY_STAGE_SQL, params)).mappings().all()

    pipeline_total = 0.0
    weighted_total = 0.0
    at_risk_total = 0.0
    won_recent = 0.0
    stage_bars: list[dict] = []

    for r in rows:
        if r["is_won"]:
            # «Закрыто за 90 дней» — только выигранные этапы.
            won_recent += float(r["won_recent"])
            continue
        if r["is_lost"]:
            continue
        total = float(r["total"])
        pipeline_total += total
        weighted_total += total * float(r["probability"] or 0) / 100
        at_risk_total += float(r["at_risk_total"])
        stage_bars.append(
            {
                "stage_id": r["stage_id"],
                "name": r["stage_name"],
                "total": total,
                "count": r["lead_count"],
            }
        )

    deals = (
        await db.execute(_FORECAST_AT_RISK_SQL, {**params, "limit": AT_RISK_LIMIT})
    ).mappings().all()

    return {
        "pipeline_total": pipeline_total,
        "weighted_total": weighted_total,
        "at_risk_total": at_risk_total,
        "won_recent": won_recent,
        "stage_bars": stage_bars,
        "at_risk_deals": [
            {
                "id": d["id"],
                "company_name": d["company_name"],
                "amount": float(d["amount"]),
                "overdue_days": d["overdue_days"],
                "stage_name": d["stage_name"],
            }
            for d in deals
        ],
    }
