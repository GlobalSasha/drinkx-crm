"""Tests for app/enrichment/budget.py — daily AI budget guard."""
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

def test_daily_cap_is_monthly_div_30():
    """_daily_cap_usd() == ai_monthly_budget_usd / 30."""
    from app.enrichment.budget import _daily_cap_usd

    mock_settings = MagicMock()
    mock_settings.ai_monthly_budget_usd = 200.0
    with patch("app.enrichment.budget.get_settings", return_value=mock_settings):
        cap = _daily_cap_usd()
    assert abs(cap - 200.0 / 30.0) < 1e-9


@pytest.mark.asyncio
async def test_has_budget_remaining_true_initially():
    """has_budget_remaining returns True when Redis key is absent (zero spend)."""
    from app.enrichment.budget import has_budget_remaining

    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value=None)

    mock_settings = MagicMock()
    mock_settings.ai_monthly_budget_usd = 200.0

    with (
        patch("app.enrichment.budget.get_redis", return_value=redis_mock),
        patch("app.enrichment.budget.get_settings", return_value=mock_settings),
    ):
        result = await has_budget_remaining(uuid.uuid4())

    assert result is True


@pytest.mark.asyncio
async def test_add_to_daily_spend_increments_counter():
    """add_to_daily_spend calls incrbyfloat and expire on the Redis client."""
    from app.enrichment.budget import add_to_daily_spend

    redis_mock = AsyncMock()
    redis_mock.incrbyfloat = AsyncMock(return_value=0.05)
    redis_mock.expire = AsyncMock(return_value=True)

    with patch("app.enrichment.budget.get_redis", return_value=redis_mock):
        await add_to_daily_spend(uuid.uuid4(), 0.05)

    redis_mock.incrbyfloat.assert_called_once()
    redis_mock.expire.assert_called_once()


@pytest.mark.asyncio
async def test_add_to_daily_spend_skips_zero_cost():
    """add_to_daily_spend does nothing when cost_usd <= 0."""
    from app.enrichment.budget import add_to_daily_spend

    redis_mock = AsyncMock()

    with patch("app.enrichment.budget.get_redis", return_value=redis_mock):
        await add_to_daily_spend(uuid.uuid4(), 0.0)

    redis_mock.incrbyfloat.assert_not_called()


@pytest.mark.asyncio
async def test_has_budget_remaining_false_when_exceeded():
    """has_budget_remaining returns False when spend >= daily cap."""
    from app.enrichment.budget import has_budget_remaining

    redis_mock = AsyncMock()
    # Spent more than the daily cap
    redis_mock.get = AsyncMock(return_value="9999.99")

    mock_settings = MagicMock()
    mock_settings.ai_monthly_budget_usd = 200.0

    with (
        patch("app.enrichment.budget.get_redis", return_value=redis_mock),
        patch("app.enrichment.budget.get_settings", return_value=mock_settings),
    ):
        result = await has_budget_remaining(uuid.uuid4())

    assert result is False
