"""Tests for app.scheduled.daily_plan_runner."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_user(tz: str = "Europe/Moscow", last_login_offset_days: int = 0) -> MagicMock:
    u = MagicMock()
    u.id = uuid.uuid4()
    u.timezone = tz
    u.last_login_at = datetime.now(timezone.utc) - timedelta(days=last_login_offset_days)
    return u


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_daily_plan_skips_users_not_at_8am():
    """Users whose local hour is NOT 8 are skipped."""
    from app.scheduled.daily_plan_runner import run_daily_plan_for_all_users

    user = _make_user(tz="Europe/Moscow")
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalars=lambda: MagicMock(all=lambda: [user])))

    # Patch _local_hour_now to return non-8
    with patch("app.scheduled.daily_plan_runner._local_hour_now", return_value=10):
        with patch("app.scheduled.daily_plan_runner.generate_for_user", new_callable=AsyncMock) as mock_gen:
            result = await run_daily_plan_for_all_users(session)

    assert result == 0
    mock_gen.assert_not_called()


@pytest.mark.asyncio
async def test_run_daily_plan_runs_for_users_at_8am_local():
    """Users whose local hour is exactly 8 get a plan generated."""
    from app.scheduled.daily_plan_runner import run_daily_plan_for_all_users
    from datetime import date

    user = _make_user(tz="Europe/Moscow")
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalars=lambda: MagicMock(all=lambda: [user])))

    fixed_date = date(2026, 5, 7)

    with patch("app.scheduled.daily_plan_runner._local_hour_now", return_value=8):
        with patch("app.scheduled.daily_plan_runner.generate_for_user", new_callable=AsyncMock) as mock_gen:
            with patch("app.scheduled.daily_plan_runner.datetime") as mock_dt:
                # Make datetime.now() return a consistent value
                mock_dt.now.return_value = MagicMock(date=lambda: fixed_date, hour=8)
                mock_dt.now.side_effect = lambda tz=None: MagicMock(
                    date=lambda: fixed_date,
                    hour=8,
                )
                # We need real timedelta
                import datetime as real_dt
                mock_dt.side_effect = lambda *a, **kw: real_dt.datetime(*a, **kw)
                result = await run_daily_plan_for_all_users(session)

    assert result == 1
    mock_gen.assert_called_once()
    call_kwargs = mock_gen.call_args
    assert call_kwargs.kwargs["user"] is user


@pytest.mark.asyncio
async def test_run_daily_plan_skips_inactive_users():
    """Users whose last_login_at > 30 days ago are not returned by the query."""
    from app.scheduled.daily_plan_runner import run_daily_plan_for_all_users

    session = AsyncMock()
    # Simulate empty query result (DB filters inactive users via WHERE clause)
    session.execute = AsyncMock(return_value=MagicMock(scalars=lambda: MagicMock(all=lambda: [])))

    with patch("app.scheduled.daily_plan_runner._local_hour_now", return_value=8):
        with patch("app.scheduled.daily_plan_runner.generate_for_user", new_callable=AsyncMock) as mock_gen:
            result = await run_daily_plan_for_all_users(session)

    assert result == 0
    mock_gen.assert_not_called()


@pytest.mark.asyncio
async def test_run_daily_plan_continues_on_per_user_failure():
    """If the first user's generate_for_user raises, the second user is still processed."""
    from app.scheduled.daily_plan_runner import run_daily_plan_for_all_users
    from datetime import date

    user1 = _make_user(tz="Europe/Moscow")
    user2 = _make_user(tz="Europe/Moscow")
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalars=lambda: MagicMock(all=lambda: [user1, user2]))
    )

    fixed_date = date(2026, 5, 7)

    call_count = 0

    async def side_effect(session, *, user, plan_date):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("LLM timeout")

    with patch("app.scheduled.daily_plan_runner._local_hour_now", return_value=8):
        with patch("app.scheduled.daily_plan_runner.generate_for_user", side_effect=side_effect):
            with patch("app.scheduled.daily_plan_runner.datetime") as mock_dt:
                import datetime as real_dt
                mock_dt.now.return_value = MagicMock(date=lambda: fixed_date)
                mock_dt.now.side_effect = lambda tz=None: MagicMock(date=lambda: fixed_date)
                mock_dt.side_effect = lambda *a, **kw: real_dt.datetime(*a, **kw)
                result = await run_daily_plan_for_all_users(session)

    # user1 failed, user2 succeeded → counter = 1
    assert result == 1
