"""Флаги застоя лида: `is_rotting_stage` и `is_rotting_next_step` (ADR-010).

Флаги — производные: их пересчитывает задача Celery beat раз в час
(`app.scheduled.jobs.recompute_lead_rotting`) и хук смены этапа
(`app.automation.stage_change.recompute_rotting_flags`).

Правила:
- лид «в работе» — назначен менеджеру (`assignment_status = 'assigned'`),
  не в корзине и стоит на этапе, который не won и не lost. Та же выборка,
  что у прогноза (`_FORECAST_SCOPED_CTE` в `app/leads/analytics.py`);
- `is_rotting_stage` — лид в работе, у этапа `rot_days > 0`, и дней на
  этапе больше `rot_days`. Дни на этапе считаются ровно как `stage_days`
  в прогнозе, чтобы «устаревающие» совпадали с «под риском»;
- `is_rotting_next_step` — лид в работе и `next_action_at` в прошлом.

Всё остальное — false, так что флаг снимается сам, когда условие ушло.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Пишем только строки, где флаг реально меняется: иначе каждый час
# переписывались бы все лиды workspace.
_RECOMPUTE_SQL = text(
    """
    UPDATE leads l
    SET is_rotting_stage = c.rotting_stage,
        is_rotting_next_step = c.rotting_next_step
    FROM (
        SELECT x.id,
               COALESCE(
                   x.in_work AND x.rot_days > 0 AND x.stage_days > x.rot_days,
                   false
               ) AS rotting_stage,
               COALESCE(x.in_work AND x.next_action_at < now(), false)
                   AS rotting_next_step
        FROM (
            SELECT l2.id,
                   l2.next_action_at,
                   s.rot_days,
                   (
                       l2.assignment_status = 'assigned'
                       AND l2.deleted_at IS NULL
                       AND s.id IS NOT NULL
                       AND NOT s.is_won
                       AND NOT s.is_lost
                   ) AS in_work,
                   -- Как stage_days в _FORECAST_SCOPED_CTE (app/leads/analytics.py).
                   GREATEST(
                       0,
                       FLOOR(
                           EXTRACT(EPOCH FROM (now() - COALESCE(h.entered_at, l2.created_at)))
                           / 86400
                       )
                   ) AS stage_days
            FROM leads l2
            LEFT JOIN stages s ON s.id = l2.stage_id
            LEFT JOIN LATERAL (
                SELECT lsh.entered_at
                FROM lead_stage_history lsh
                WHERE lsh.lead_id = l2.id
                  AND lsh.stage_id = l2.stage_id
                  AND lsh.exited_at IS NULL
                ORDER BY lsh.entered_at DESC
                LIMIT 1
            ) h ON true
            WHERE l2.workspace_id = :wid
        ) x
    ) c
    WHERE l.id = c.id
      AND (
          l.is_rotting_stage IS DISTINCT FROM c.rotting_stage
          OR l.is_rotting_next_step IS DISTINCT FROM c.rotting_next_step
      )
    """
)


async def recompute_workspace_rotting(db: AsyncSession, workspace_id: uuid.UUID) -> int:
    """Пересчитать флаги застоя у всех лидов workspace одним UPDATE.
    Возвращает число лидов, у которых флаг поменялся."""
    result = await db.execute(_RECOMPUTE_SQL, {"wid": str(workspace_id)})
    return result.rowcount or 0


async def recompute_all_workspaces(db: AsyncSession) -> int:
    """Пересчёт по всем workspace, коммит после каждого — чтобы не держать
    блокировки строк лидов на весь проход."""
    workspace_ids = (await db.execute(text("SELECT id FROM workspaces"))).scalars().all()
    changed = 0
    for wid in workspace_ids:
        changed += await recompute_workspace_rotting(db, wid)
        await db.commit()
    return changed


def rotting_next_step(
    *, in_work: bool, next_action_at: datetime | None, now: datetime | None = None
) -> bool:
    """`is_rotting_next_step` для одного лида — то же правило, что в UPDATE."""
    if not in_work or next_action_at is None:
        return False
    return next_action_at < (now or datetime.now(timezone.utc))
