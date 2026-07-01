"""Tests for app/enrichment/budget.py — fail-closed guard + monthly ceiling.

Covers Plan 011: `has_budget_remaining` must fail *closed* (return False)
when Redis is unreachable, and must also reject once the hard monthly
ceiling is reached even if the daily counter is under cap.
"""
from __future__ import annotations

import sys
import uuid
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Stub structlog before importing budget
# ---------------------------------------------------------------------------

def _stub_structlog():
    if "structlog" in sys.modules:
        return
    sl = ModuleType("structlog")
    class _Logger:
        def warning(self, *a, **kw): pass
        def info(self, *a, **kw): pass
        def bind(self, **kw): return self
    sl.get_logger = lambda: _Logger()
    sys.modules["structlog"] = sl

_stub_structlog()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_has_budget_remaining_true_under_cap():
    """Under both daily and monthly cap → True."""
    from app.enrichment.budget import has_budget_remaining

    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value="1.0")  # same value for day/month keys

    mock_settings = MagicMock()
    mock_settings.ai_monthly_budget_usd = 200.0

    with (
        patch("app.enrichment.budget.get_redis", return_value=redis_mock),
        patch("app.enrichment.budget.get_settings", return_value=mock_settings),
    ):
        result = await has_budget_remaining(uuid.uuid4())

    assert result is True


@pytest.mark.asyncio
async def test_has_budget_remaining_false_over_daily_cap():
    """Daily spend >= daily cap (monthly/30) → False."""
    from app.enrichment.budget import has_budget_remaining

    mock_settings = MagicMock()
    mock_settings.ai_monthly_budget_usd = 200.0
    daily_cap = 200.0 / 30.0

    async def fake_get(key: str):
        if "ai_budget_month" in key:
            return "0.0"
        return str(daily_cap + 1.0)  # over daily cap, well under monthly cap

    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(side_effect=fake_get)

    with (
        patch("app.enrichment.budget.get_redis", return_value=redis_mock),
        patch("app.enrichment.budget.get_settings", return_value=mock_settings),
    ):
        result = await has_budget_remaining(uuid.uuid4())

    assert result is False


@pytest.mark.asyncio
async def test_has_budget_remaining_false_when_redis_raises():
    """Core regression (Plan 011): Redis error → fail closed → False,
    never the old fail-open `True`.
    """
    from app.enrichment.budget import has_budget_remaining

    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(side_effect=ConnectionError("redis unreachable"))

    mock_settings = MagicMock()
    mock_settings.ai_monthly_budget_usd = 200.0

    with (
        patch("app.enrichment.budget.get_redis", return_value=redis_mock),
        patch("app.enrichment.budget.get_settings", return_value=mock_settings),
    ):
        result = await has_budget_remaining(uuid.uuid4())

    assert result is False


@pytest.mark.asyncio
async def test_has_budget_remaining_false_when_monthly_ceiling_reached():
    """Monthly spend >= ai_monthly_budget_usd → False, even though the
    daily counter alone is under the daily cap.
    """
    from app.enrichment.budget import has_budget_remaining

    mock_settings = MagicMock()
    mock_settings.ai_monthly_budget_usd = 200.0

    async def fake_get(key: str):
        if "ai_budget_month" in key:
            return "200.0"  # monthly ceiling reached
        return "0.01"  # daily spend trivially under daily cap

    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(side_effect=fake_get)

    with (
        patch("app.enrichment.budget.get_redis", return_value=redis_mock),
        patch("app.enrichment.budget.get_settings", return_value=mock_settings),
    ):
        result = await has_budget_remaining(uuid.uuid4())

    assert result is False


@pytest.mark.asyncio
async def test_add_to_daily_spend_increments_both_day_and_month_keys():
    """add_to_daily_spend increments the daily counter and the monthly
    ceiling counter, each with its own TTL.
    """
    from app.enrichment.budget import add_to_daily_spend

    redis_mock = AsyncMock()
    redis_mock.incrbyfloat = AsyncMock(return_value=0.05)
    redis_mock.expire = AsyncMock(return_value=True)

    with patch("app.enrichment.budget.get_redis", return_value=redis_mock):
        await add_to_daily_spend(uuid.uuid4(), 0.05)

    assert redis_mock.incrbyfloat.call_count == 2
    assert redis_mock.expire.call_count == 2

    incr_keys = [call.args[0] for call in redis_mock.incrbyfloat.call_args_list]
    assert any("ai_budget_month" in k for k in incr_keys)
    assert any("ai_budget_month" not in k and "ai_budget" in k for k in incr_keys)
