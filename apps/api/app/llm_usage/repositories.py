"""llm_usage persistence + aggregation."""
from __future__ import annotations

import datetime as _dt
import uuid
from decimal import Decimal
from typing import Literal

from sqlalchemy import func, select

from app.llm_usage.models import LlmUsage

Period = Literal["this_month", "last_month", "all"]


def insert_usage(
    db,
    *,
    workspace_id: uuid.UUID,
    task_type: str,
    provider: str,
    model: str | None,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: Decimal,
) -> None:
    """Stage a usage row on the caller's session — add() ONLY, no flush/commit.

    add() emits no SQL, so it cannot poison the caller's in-flight transaction
    and cannot commit the caller's other pending changes. The row persists when
    the caller commits its own transaction (every LLM call site commits right
    after the call). If the caller rolls back, the telemetry row is dropped too
    — acceptable for best-effort cost tracking.
    """
    db.add(
        LlmUsage(
            workspace_id=workspace_id,
            task_type=task_type,
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
        )
    )


def period_bounds(
    period: Period, *, now: _dt.datetime | None = None
) -> tuple[_dt.datetime | None, _dt.datetime | None]:
    """Return [start, end) UTC bounds for a period. `all` → (None, None)."""
    now = now or _dt.datetime.now(tz=_dt.timezone.utc)
    if period == "all":
        return None, None
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if period == "this_month":
        # next month start
        if month_start.month == 12:
            nxt = month_start.replace(year=month_start.year + 1, month=1)
        else:
            nxt = month_start.replace(month=month_start.month + 1)
        return month_start, nxt
    # last_month
    if month_start.month == 1:
        prev = month_start.replace(year=month_start.year - 1, month=12)
    else:
        prev = month_start.replace(month=month_start.month - 1)
    return prev, month_start


async def aggregate_by_provider(
    db,
    *,
    workspace_id,
    start: _dt.datetime | None,
    end: _dt.datetime | None,
) -> list[tuple[str, float, int]]:
    """Return [(provider, total_cost_usd, call_count), ...] for the window."""
    stmt = select(
        LlmUsage.provider,
        func.coalesce(func.sum(LlmUsage.cost_usd), 0),
        func.count(LlmUsage.id),
    ).where(LlmUsage.workspace_id == workspace_id)
    if start is not None:
        stmt = stmt.where(LlmUsage.created_at >= start)
    if end is not None:
        stmt = stmt.where(LlmUsage.created_at < end)
    stmt = stmt.group_by(LlmUsage.provider)

    res = await db.execute(stmt)
    return [(row[0], float(row[1]), int(row[2])) for row in res.all()]
