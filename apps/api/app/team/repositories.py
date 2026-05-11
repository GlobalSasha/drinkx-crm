"""Team stats aggregations — Sprint 3.4 G1.

Raw SQL keyed by user_id. All counts are workspace-scoped — either
directly via a workspace_id column (leads, audit_log) or transitively
via users.workspace_id (activities → users.user_id).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def kp_sent_per_user(
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
          AND a.type = 'file'
          AND a.file_kind = 'kp'
          AND a.created_at >= :from_ AND a.created_at <= :to
        GROUP BY a.user_id
    """)
    rows = (await db.execute(
        sql, {"wid": workspace_id, "uids": user_ids, "from_": from_, "to": to}
    )).all()
    return {r.user_id: int(r.n) for r in rows}


async def leads_taken_per_user(
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
          AND assignment_status = 'assigned'
          AND updated_at >= :from_ AND updated_at <= :to
        GROUP BY assigned_to
    """)
    rows = (await db.execute(
        sql, {"wid": workspace_id, "uids": user_ids, "from_": from_, "to": to}
    )).all()
    return {r.user_id: int(r.n) for r in rows}


async def leads_moved_per_user(
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
        SELECT user_id, count(*) AS n
        FROM audit_log
        WHERE workspace_id = :wid
          AND user_id = ANY(:uids)
          AND action = 'lead.move_stage'
          AND created_at >= :from_ AND created_at <= :to
        GROUP BY user_id
    """)
    rows = (await db.execute(
        sql, {"wid": workspace_id, "uids": user_ids, "from_": from_, "to": to}
    )).all()
    return {r.user_id: int(r.n) for r in rows}


async def tasks_completed_per_user(
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
          AND a.type = 'task'
          AND a.task_done = true
          AND a.task_completed_at >= :from_ AND a.task_completed_at <= :to
        GROUP BY a.user_id
    """)
    rows = (await db.execute(
        sql, {"wid": workspace_id, "uids": user_ids, "from_": from_, "to": to}
    )).all()
    return {r.user_id: int(r.n) for r in rows}


async def last_active_per_user(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_ids: list[uuid.UUID],
) -> dict[uuid.UUID, datetime]:
    """Most recent activity row authored by the user. Falls back to
    last_login_at in the service layer if no rows."""
    if not user_ids:
        return {}
    sql = text("""
        SELECT a.user_id, max(a.created_at) AS ts
        FROM activities a
        JOIN users u ON u.id = a.user_id
        WHERE u.workspace_id = :wid
          AND a.user_id = ANY(:uids)
        GROUP BY a.user_id
    """)
    rows = (await db.execute(
        sql, {"wid": workspace_id, "uids": user_ids}
    )).all()
    return {r.user_id: r.ts for r in rows}


# ---------------------------------------------------------------------------
# Daily breakdown for a single user
# ---------------------------------------------------------------------------

async def daily_breakdown(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    from_: datetime,
    to: datetime,
) -> list[dict]:
    """Return one row per day in [from_, to] with the four counts.

    Days with zero events are omitted (the frontend can fill gaps if
    needed). Sorted ascending by date.
    """
    sql = text("""
        WITH params AS (
            SELECT :wid::uuid AS wid, :uid::uuid AS uid,
                   :from_::timestamptz AS d_from, :to::timestamptz AS d_to
        ),
        kp AS (
            SELECT (a.created_at AT TIME ZONE 'UTC')::date AS d, count(*) AS n
            FROM activities a, params p
            WHERE a.user_id = p.uid
              AND a.type = 'file' AND a.file_kind = 'kp'
              AND a.created_at >= p.d_from AND a.created_at <= p.d_to
            GROUP BY 1
        ),
        taken AS (
            SELECT (l.updated_at AT TIME ZONE 'UTC')::date AS d, count(*) AS n
            FROM leads l, params p
            WHERE l.workspace_id = p.wid
              AND l.assigned_to = p.uid
              AND l.assignment_status = 'assigned'
              AND l.updated_at >= p.d_from AND l.updated_at <= p.d_to
            GROUP BY 1
        ),
        moved AS (
            SELECT (al.created_at AT TIME ZONE 'UTC')::date AS d, count(*) AS n
            FROM audit_log al, params p
            WHERE al.workspace_id = p.wid
              AND al.user_id = p.uid
              AND al.action = 'lead.move_stage'
              AND al.created_at >= p.d_from AND al.created_at <= p.d_to
            GROUP BY 1
        ),
        tasks AS (
            SELECT (a.task_completed_at AT TIME ZONE 'UTC')::date AS d, count(*) AS n
            FROM activities a, params p
            WHERE a.user_id = p.uid
              AND a.type = 'task' AND a.task_done = true
              AND a.task_completed_at >= p.d_from AND a.task_completed_at <= p.d_to
            GROUP BY 1
        ),
        all_days AS (
            SELECT d FROM kp
            UNION SELECT d FROM taken
            UNION SELECT d FROM moved
            UNION SELECT d FROM tasks
        )
        SELECT d.d AS day,
               COALESCE(kp.n, 0)    AS kp_sent,
               COALESCE(taken.n, 0) AS leads_taken_from_pool,
               COALESCE(moved.n, 0) AS leads_moved,
               COALESCE(tasks.n, 0) AS tasks_completed
        FROM all_days d
        LEFT JOIN kp    ON kp.d    = d.d
        LEFT JOIN taken ON taken.d = d.d
        LEFT JOIN moved ON moved.d = d.d
        LEFT JOIN tasks ON tasks.d = d.d
        ORDER BY d.d ASC
    """)
    rows = (await db.execute(
        sql,
        {"wid": workspace_id, "uid": user_id, "from_": from_, "to": to},
    )).all()
    return [
        {
            "date": r.day,
            "kp_sent": int(r.kp_sent),
            "leads_taken_from_pool": int(r.leads_taken_from_pool),
            "leads_moved": int(r.leads_moved),
            "tasks_completed": int(r.tasks_completed),
        }
        for r in rows
    ]
