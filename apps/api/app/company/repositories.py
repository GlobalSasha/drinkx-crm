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
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    today_start: datetime,
    yesterday_start: datetime,
    week_start: datetime,
    prior_week_start: datetime,
) -> dict:
    """today / yesterday / trailing-7d, plus the 7 days before that (week_prior)
    for the week-over-week delta."""
    sql = text("""
        SELECT
          count(*) FILTER (WHERE created_at >= :today_start)                               AS today,
          count(*) FILTER (WHERE created_at >= :yest_start AND created_at < :today_start)   AS yesterday,
          count(*) FILTER (WHERE created_at >= :week_start)                                 AS week,
          count(*) FILTER (WHERE created_at >= :prior_week_start AND created_at < :week_start) AS week_prior
        FROM leads
        WHERE workspace_id = :wid AND archived_at IS NULL
    """)
    r = (await db.execute(sql, {
        "wid": workspace_id, "today_start": today_start,
        "yest_start": yesterday_start, "week_start": week_start,
        "prior_week_start": prior_week_start,
    })).one()
    return {"today": int(r.today), "yesterday": int(r.yesterday), "week": int(r.week), "week_prior": int(r.week_prior)}


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
    db: AsyncSession, *, workspace_id: uuid.UUID, from_: datetime, to_: datetime | None = None
) -> list[dict]:
    """Per-source lead + qualified counts for leads created in [from_, to_).

    `to_` is exclusive; omit it for the open-ended current window (through now).
    """
    # Build the upper bound only when present — passing a NULL param makes
    # asyncpg unable to infer its type (AmbiguousParameterError).
    upper = "AND l.created_at < :to_" if to_ is not None else ""
    sql = text(f"""
        SELECT ls.id AS source_id, ls.name AS name, COALESCE(ls.is_paid, false) AS is_paid,
               count(*)                          AS leads,
               count(*) FILTER (WHERE s.position > 0) AS qualified
        FROM leads l
        LEFT JOIN lead_sources ls ON ls.id = l.source_id
        LEFT JOIN stages s ON s.id = l.stage_id
        WHERE l.workspace_id = :wid AND l.archived_at IS NULL AND l.created_at >= :from_
          {upper}
        GROUP BY ls.id, ls.name, ls.is_paid
        ORDER BY leads DESC
    """)
    params: dict = {"wid": workspace_id, "from_": from_}
    if to_ is not None:
        params["to_"] = to_
    rows = (await db.execute(sql, params)).all()
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
               ls.name AS source_name, u.name AS manager_name, s.name AS stage_name,
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
            "stage_name": r.stage_name,
            "days_idle": int(r.days_idle),
        }
        for r in rows
    ]


async def manager_load(db: AsyncSession, *, workspace_id: uuid.UUID) -> list[dict]:
    sql = text(f"""
        SELECT l.assigned_to AS uid, u.name AS name, u.max_active_deals AS max_active_deals,
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
        GROUP BY l.assigned_to, u.name, u.max_active_deals
        ORDER BY in_work DESC
    """)
    rows = (await db.execute(sql, {"wid": workspace_id})).all()
    return [
        {
            "user_id": r.uid,
            "name": r.name or "—",
            "max_active_deals": int(r.max_active_deals) if r.max_active_deals is not None else None,
            "in_work": int(r.in_work),
            "new_week": int(r.new_week),
            "stuck": int(r.stuck),
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Per-manager work + result metrics (CEO managers dashboard)
# ---------------------------------------------------------------------------


async def manager_roster(db: AsyncSession, *, workspace_id: uuid.UUID) -> list[dict]:
    """All managers in the workspace, ordered by name."""
    sql = text("""
        SELECT u.id AS user_id, u.name AS name, u.role AS role,
               u.last_login_at AS last_login_at
        FROM users u
        WHERE u.workspace_id = :wid AND u.role = 'manager'
        ORDER BY u.name
    """)
    rows = (await db.execute(sql, {"wid": workspace_id})).all()
    return [
        {
            "user_id": r.user_id,
            "name": r.name,
            "role": r.role,
            "last_login_at": r.last_login_at,
        }
        for r in rows
    ]


async def new_leads_per_user(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_ids: list[uuid.UUID],
    from_: datetime,
    to: datetime,
) -> dict[uuid.UUID, int]:
    if not user_ids:
        return {}
    sql = text("""
        SELECT assigned_to AS user_id, count(*) AS n
        FROM leads
        WHERE workspace_id = :wid
          AND assigned_to = ANY(:uids)
          AND created_at >= :from_ AND created_at <= :to
          AND archived_at IS NULL
        GROUP BY assigned_to
    """)
    rows = (
        await db.execute(
            sql, {"wid": workspace_id, "uids": user_ids, "from_": from_, "to": to}
        )
    ).all()
    return {r.user_id: int(r.n) for r in rows}


async def actions_per_user(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_ids: list[uuid.UUID],
    from_: datetime,
    to: datetime,
) -> dict[uuid.UUID, int]:
    if not user_ids:
        return {}
    sql = text("""
        SELECT a.user_id, count(*) AS n
        FROM activities a
        JOIN users u ON u.id = a.user_id
        WHERE u.workspace_id = :wid
          AND a.user_id = ANY(:uids)
          AND a.created_at >= :from_ AND a.created_at <= :to
          AND a.type IN (
            'comment','task','reminder','file','email','tg','phone','form_submission'
          )
        GROUP BY a.user_id
    """)
    rows = (
        await db.execute(
            sql, {"wid": workspace_id, "uids": user_ids, "from_": from_, "to": to}
        )
    ).all()
    return {r.user_id: int(r.n) for r in rows}


async def tasks_overdue_per_user(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_ids: list[uuid.UUID],
) -> dict[uuid.UUID, int]:
    """Point-in-time overdue task count on leads assigned to each user."""
    if not user_ids:
        return {}
    sql = text("""
        SELECT l.assigned_to AS user_id, count(*) AS n
        FROM activities a
        JOIN leads l ON l.id = a.lead_id
        WHERE l.workspace_id = :wid
          AND l.assigned_to = ANY(:uids)
          AND a.type = 'task'
          AND a.task_done = false
          AND a.task_due_at < now()
        GROUP BY l.assigned_to
    """)
    rows = (await db.execute(sql, {"wid": workspace_id, "uids": user_ids})).all()
    return {r.user_id: int(r.n) for r in rows}


async def portfolio_per_user(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_ids: list[uuid.UUID],
) -> dict[uuid.UUID, dict]:
    """Batched portfolio KPI over active assigned non-terminal leads."""
    if not user_ids:
        return {}
    sql = text("""
        SELECT l.assigned_to AS user_id,
               count(*) AS in_work,
               count(*) FILTER (
                 WHERE l.is_rotting_stage OR l.is_rotting_next_step
               ) AS stuck,
               COALESCE(
                 MAX(
                   EXTRACT(DAY FROM now() - COALESCE(l.last_activity_at, l.created_at))::int
                 ) FILTER (WHERE l.is_rotting_stage OR l.is_rotting_next_step),
                 0
               ) AS oldest_stuck_days
        FROM leads l
        JOIN stages s ON s.id = l.stage_id
        WHERE l.workspace_id = :wid
          AND l.assigned_to = ANY(:uids)
          AND l.assignment_status = 'assigned'
          AND l.archived_at IS NULL
          AND s.is_won = false AND s.is_lost = false
        GROUP BY l.assigned_to
    """)
    rows = (await db.execute(sql, {"wid": workspace_id, "uids": user_ids})).all()
    return {
        r.user_id: {
            "in_work": int(r.in_work),
            "stuck": int(r.stuck),
            "oldest_stuck_days": int(r.oldest_stuck_days or 0),
        }
        for r in rows
    }


async def workspace_has_leads(db: AsyncSession, *, workspace_id: uuid.UUID) -> bool:
    """Cheap existence check — gates silent-manager alerts."""
    sql = text("SELECT EXISTS(SELECT 1 FROM leads WHERE workspace_id = :wid)")
    return bool((await db.execute(sql, {"wid": workspace_id})).scalar_one())
