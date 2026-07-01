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
_MONTH_KEY_PREFIX = "ai_budget_month"
_MONTH_TTL_SECONDS = 60 * 60 * 24 * 40  # ~40 days — covers month-boundary slack


def _key(workspace_id: uuid.UUID, day: str | None = None) -> str:
    day = day or _dt.datetime.utcnow().strftime("%Y-%m-%d")
    return f"{_KEY_PREFIX}:{workspace_id}:{day}"


def _month_key(workspace_id: uuid.UUID, month: str | None = None) -> str:
    month = month or _dt.datetime.utcnow().strftime("%Y-%m")
    return f"{_MONTH_KEY_PREFIX}:{workspace_id}:{month}"


def _daily_cap_usd() -> float:
    s = get_settings()
    return float(s.ai_monthly_budget_usd) / 30.0


def _monthly_cap_usd() -> float:
    s = get_settings()
    return float(s.ai_monthly_budget_usd)


async def get_daily_spend_usd(workspace_id: uuid.UUID) -> float:
    """Best-effort read of today's spend. Returns 0.0 on Redis error —
    callers that display this (e.g. the settings dashboard) must not 500
    on a Redis blip. Budget *enforcement* does its own fail-closed check
    in `has_budget_remaining` instead of trusting this return value.
    """
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
        day_key = _key(workspace_id)
        month_key = _month_key(workspace_id)
        # INCRBYFLOAT is atomic; SET TTL on first hit
        await client.incrbyfloat(day_key, cost_usd)
        await client.expire(day_key, _DAY_TTL_SECONDS)
        await client.incrbyfloat(month_key, cost_usd)
        await client.expire(month_key, _MONTH_TTL_SECONDS)
    except Exception as e:
        log.warning("budget.add_failed", error=str(e))


async def has_budget_remaining(workspace_id: uuid.UUID) -> bool:
    """Pre-flight budget check. Fails **closed**: if Redis can't be
    reached, spend is unknown, so we treat it as no budget remaining
    rather than uncapped spend (Plan 011 — Redis blips must pause
    enrichment, not silently disable the cost guard).
    """
    try:
        client = get_redis()
        raw_day = await client.get(_key(workspace_id))
        raw_month = await client.get(_month_key(workspace_id))
    except Exception as e:
        log.warning("budget.read_failed_fail_closed", error=str(e))
        return False

    spent_day = float(raw_day) if raw_day else 0.0
    spent_month = float(raw_month) if raw_month else 0.0

    if spent_month >= _monthly_cap_usd():
        return False
    return spent_day < _daily_cap_usd()
