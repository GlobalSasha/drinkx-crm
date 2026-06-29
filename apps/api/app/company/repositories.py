"""Raw-SQL aggregates for the company overview. Workspace-scoped, read-only.

«Qualified» = a lead that has left the intake stage (stage.position > 0) — the
intake stage is always position 0 (get_default_first_stage). «Stuck» = an open
assigned lead on a non-terminal stage with no touch for 7+ days.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

STUCK_DAYS = 7


async def pulse_counts(
    db: AsyncSession, *, workspace_id: uuid.UUID, today_start: datetime, yesterday_start: datetime, week_start: datetime
) -> dict:
    sql = text("""
        SELECT
          count(*) FILTER (WHERE created_at >= :today_start)                               AS today,
          count(*) FILTER (WHERE created_at >= :yest_start AND created_at < :today_start)   AS yesterday,
          count(*) FILTER (WHERE created_at >= :week_start)                                 AS week
        FROM leads
        WHERE workspace_id = :wid AND archived_at IS NULL
    """)
    r = (await db.execute(sql, {
        "wid": workspace_id, "today_start": today_start,
        "yest_start": yesterday_start, "week_start": week_start,
    })).one()
    return {"today": int(r.today), "yesterday": int(r.yesterday), "week": int(r.week)}


async def stuck_count(db: AsyncSession, *, workspace_id: uuid.UUID) -> int:
    sql = text(f"""
        SELECT count(*)
        FROM leads l JOIN stages s ON s.id = l.stage_id
        WHERE l.workspace_id = :wid
          AND l.assignment_status = 'assigned'
          AND l.archived_at IS NULL
          AND s.is_won = false AND s.is_lost = false
          AND COALESCE(l.last_activity_at, l.created_at) < now() - interval '{STUCK_DAYS} days'
    """)
    return int((await db.execute(sql, {"wid": workspace_id})).scalar_one())


async def source_breakdown(
    db: AsyncSession, *, workspace_id: uuid.UUID, from_: datetime
) -> list[dict]:
    """Per-source lead + qualified counts for leads created since `from_`."""
    sql = text("""
        SELECT ls.id AS source_id, ls.name AS name, COALESCE(ls.is_paid, false) AS is_paid,
               count(*)                          AS leads,
               count(*) FILTER (WHERE s.position > 0) AS qualified
        FROM leads l
        LEFT JOIN lead_sources ls ON ls.id = l.source_id
        LEFT JOIN stages s ON s.id = l.stage_id
        WHERE l.workspace_id = :wid AND l.archived_at IS NULL AND l.created_at >= :from_
        GROUP BY ls.id, ls.name, ls.is_paid
        ORDER BY leads DESC
    """)
    rows = (await db.execute(sql, {"wid": workspace_id, "from_": from_})).all()
    return [
        {
            "source_id": r.source_id,
            "name": r.name,
            "is_paid": bool(r.is_paid),
            "leads": int(r.leads),
            "qualified": int(r.qualified),
        }
        for r in rows
    ]


async def daily_by_source(
    db: AsyncSession, *, workspace_id: uuid.UUID, from_: datetime
) -> list[dict]:
    sql = text("""
        SELECT date_trunc('day', l.created_at)::date AS day, l.source_id AS source_id,
               count(*) AS cnt
        FROM leads l
        WHERE l.workspace_id = :wid AND l.archived_at IS NULL AND l.created_at >= :from_
        GROUP BY day, l.source_id
        ORDER BY day
    """)
    rows = (await db.execute(sql, {"wid": workspace_id, "from_": from_})).all()
    return [{"date": r.day, "source_id": r.source_id, "count": int(r.cnt)} for r in rows]


async def stuck_leads(
    db: AsyncSession, *, workspace_id: uuid.UUID, limit: int = 30
) -> list[dict]:
    sql = text(f"""
        SELECT l.id AS lead_id, l.company_name AS company_name,
               ls.name AS source_name, u.name AS manager_name,
               EXTRACT(DAY FROM now() - COALESCE(l.last_activity_at, l.created_at))::int AS days_idle
        FROM leads l
        JOIN stages s ON s.id = l.stage_id
        LEFT JOIN lead_sources ls ON ls.id = l.source_id
        LEFT JOIN users u ON u.id = l.assigned_to
        WHERE l.workspace_id = :wid
          AND l.assignment_status = 'assigned'
          AND l.archived_at IS NULL
          AND s.is_won = false AND s.is_lost = false
          AND COALESCE(l.last_activity_at, l.created_at) < now() - interval '{STUCK_DAYS} days'
        ORDER BY COALESCE(l.last_activity_at, l.created_at) ASC
        LIMIT :limit
    """)
    rows = (await db.execute(sql, {"wid": workspace_id, "limit": limit})).all()
    return [
        {
            "lead_id": r.lead_id,
            "company_name": r.company_name,
            "source_name": r.source_name,
            "manager_name": r.manager_name,
            "days_idle": int(r.days_idle),
        }
        for r in rows
    ]


async def manager_load(db: AsyncSession, *, workspace_id: uuid.UUID) -> list[dict]:
    sql = text(f"""
        SELECT l.assigned_to AS uid, u.name AS name,
               count(*) FILTER (WHERE s.is_won = false AND s.is_lost = false) AS in_work,
               count(*) FILTER (WHERE l.created_at >= now() - interval '7 days') AS new_week,
               count(*) FILTER (
                 WHERE s.is_won = false AND s.is_lost = false
                   AND COALESCE(l.last_activity_at, l.created_at) < now() - interval '{STUCK_DAYS} days'
               ) AS stuck
        FROM leads l
        JOIN stages s ON s.id = l.stage_id
        LEFT JOIN users u ON u.id = l.assigned_to
        WHERE l.workspace_id = :wid
          AND l.assignment_status = 'assigned'
          AND l.archived_at IS NULL
          AND l.assigned_to IS NOT NULL
        GROUP BY l.assigned_to, u.name
        ORDER BY in_work DESC
    """)
    rows = (await db.execute(sql, {"wid": workspace_id})).all()
    return [
        {
            "user_id": r.uid,
            "name": r.name or "—",
            "in_work": int(r.in_work),
            "new_week": int(r.new_week),
            "stuck": int(r.stuck),
        }
        for r in rows
    ]
