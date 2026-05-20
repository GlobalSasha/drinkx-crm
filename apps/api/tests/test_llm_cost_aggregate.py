"""Sprint 4.0 — period bounds + provider aggregation."""
from __future__ import annotations

import datetime as _dt
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.test_webforms import _stub_sqlalchemy  # type: ignore

_stub_sqlalchemy()


def test_period_bounds_this_month():
    from app.llm_usage.repositories import period_bounds

    now = _dt.datetime(2026, 5, 20, 9, 0, tzinfo=_dt.timezone.utc)
    start, end = period_bounds("this_month", now=now)
    assert start == _dt.datetime(2026, 5, 1, tzinfo=_dt.timezone.utc)
    assert end == _dt.datetime(2026, 6, 1, tzinfo=_dt.timezone.utc)


def test_period_bounds_last_month_january_wraps():
    from app.llm_usage.repositories import period_bounds

    now = _dt.datetime(2026, 1, 10, tzinfo=_dt.timezone.utc)
    start, end = period_bounds("last_month", now=now)
    assert start == _dt.datetime(2025, 12, 1, tzinfo=_dt.timezone.utc)
    assert end == _dt.datetime(2026, 1, 1, tzinfo=_dt.timezone.utc)


def test_period_bounds_this_month_december_wraps():
    from app.llm_usage.repositories import period_bounds

    now = _dt.datetime(2026, 12, 15, tzinfo=_dt.timezone.utc)
    start, end = period_bounds("this_month", now=now)
    assert start == _dt.datetime(2026, 12, 1, tzinfo=_dt.timezone.utc)
    assert end == _dt.datetime(2027, 1, 1, tzinfo=_dt.timezone.utc)


def test_period_bounds_all_is_unbounded():
    from app.llm_usage.repositories import period_bounds

    assert period_bounds("all") == (None, None)


@pytest.mark.asyncio
async def test_aggregate_by_provider_maps_rows():
    from app.llm_usage import repositories as repo

    db = MagicMock()
    db.execute = AsyncMock(
        return_value=MagicMock(all=lambda: [("mimo", 40.2, 980), ("anthropic", 5.1, 42)])
    )
    rows = await repo.aggregate_by_provider(
        db, workspace_id=uuid.uuid4(), start=None, end=None
    )
    assert rows == [("mimo", 40.2, 980), ("anthropic", 5.1, 42)]
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_aggregate_by_provider_with_bounds_runs_filtered():
    from app.llm_usage import repositories as repo

    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(all=lambda: [("mimo", 1.0, 3)]))
    start = _dt.datetime(2026, 5, 1, tzinfo=_dt.timezone.utc)
    end = _dt.datetime(2026, 6, 1, tzinfo=_dt.timezone.utc)
    rows = await repo.aggregate_by_provider(db, workspace_id=uuid.uuid4(), start=start, end=end)
    assert rows == [("mimo", 1.0, 3)]
    db.execute.assert_awaited_once()
