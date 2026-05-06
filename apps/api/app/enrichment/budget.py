"""Daily AI budget guard — Redis counter per workspace per day."""
from __future__ import annotations

import datetime as _dt
import uuid

import structlog

from app.config import get_settings
from app.enrichment.sources.cache import get_redis

log = structlog.get_logger()

_KEY_PREFIX = "ai_budget"
_DAY_TTL_SECONDS = 60 * 60 * 36  # 36h — covers timezone slack


def _key(workspace_id: uuid.UUID, day: str | None = None) -> str:
    day = day or _dt.datetime.utcnow().strftime("%Y-%m-%d")
    return f"{_KEY_PREFIX}:{workspace_id}:{day}"


def _daily_cap_usd() -> float:
    s = get_settings()
    return float(s.ai_monthly_budget_usd) / 30.0


async def get_daily_spend_usd(workspace_id: uuid.UUID) -> float:
    try:
        client = get_redis()
        raw = await client.get(_key(workspace_id))
        return float(raw) if raw else 0.0
    except Exception as e:
        log.warning("budget.read_failed", error=str(e))
        return 0.0


async def add_to_daily_spend(workspace_id: uuid.UUID, cost_usd: float) -> None:
    if cost_usd <= 0:
        return
    try:
        client = get_redis()
        key = _key(workspace_id)
        # INCRBYFLOAT is atomic; SET TTL on first hit
        await client.incrbyfloat(key, cost_usd)
        await client.expire(key, _DAY_TTL_SECONDS)
    except Exception as e:
        log.warning("budget.add_failed", error=str(e))


async def has_budget_remaining(workspace_id: uuid.UUID) -> bool:
    spent = await get_daily_spend_usd(workspace_id)
    return spent < _daily_cap_usd()
