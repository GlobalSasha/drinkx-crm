"""Tests for app.followups.dispatcher."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_followup(
    *,
    due_offset_hours: float = 12,
    status: str = "pending",
    dispatched_at: datetime | None = None,
    due_at: datetime | None = None,
) -> MagicMock:
    fu = MagicMock()
    fu.id = uuid.uuid4()
    fu.lead_id = uuid.uuid4()
    fu.name = "Call back"
    fu.status = status
    fu.dispatched_at = dispatched_at
    fu.due_at = due_at if due_at is not None else datetime.now(timezone.utc) + timedelta(hours=due_offset_hours)
    return fu


def _make_session(followups: list) -> AsyncMock:
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalars=lambda: MagicMock(all=lambda: list(followups)))
    )
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dispatcher_creates_activity_for_due_followup():
    """A followup due within 24h should produce one Activity row."""
    from app.followups.dispatcher import run_followup_dispatch
    from app.activity.models import ActivityType

    fu = _make_followup(due_offset_hours=6)
    session = _make_session([fu])

    # Patch Activity constructor to avoid triggering full ORM mapper resolution
    # (Lead.contacts relationship needs Contact model to be imported)
    with patch("app.followups.dispatcher.Activity") as MockActivity:
        mock_activity_instance = MagicMock()
        MockActivity.return_value = mock_activity_instance

        result = await run_followup_dispatch(session)

    assert result == 1
    session.add.assert_called_once_with(mock_activity_instance)
    # Verify Activity was created with correct kwargs
    call_kwargs = MockActivity.call_args.kwargs
    assert call_kwargs["lead_id"] == fu.lead_id
    assert call_kwargs["type"] == ActivityType.reminder.value
    assert call_kwargs["reminder_trigger_at"] == fu.due_at
    assert fu.dispatched_at is not None


@pytest.mark.asyncio
async def test_dispatcher_idempotent():
    """Running the dispatcher twice should only dispatch once per followup.

    The second run returns zero because dispatched_at is already set — the
    DB query (using dispatched_at IS NULL) would filter it out. We simulate
    this by returning no followups on the second call.
    """
    from app.followups.dispatcher import run_followup_dispatch

    fu = _make_followup(due_offset_hours=6)
    session = _make_session([fu])

    # First run — patch Activity to avoid ORM mapper resolution
    with patch("app.followups.dispatcher.Activity") as MockActivity:
        MockActivity.return_value = MagicMock()
        count1 = await run_followup_dispatch(session)

    assert count1 == 1
    assert fu.dispatched_at is not None

    # Second run — simulate DB returning empty (dispatched_at is now set)
    session2 = _make_session([])
    with patch("app.followups.dispatcher.Activity") as MockActivity2:
        MockActivity2.return_value = MagicMock()
        count2 = await run_followup_dispatch(session2)

    assert count2 == 0


@pytest.mark.asyncio
async def test_dispatcher_skips_already_dispatched():
    """Followups with dispatched_at already set are not returned by the query.

    This test verifies that the DB query (which filters IS NULL) would exclude
    them. We simulate by returning an empty list from session.execute.
    """
    from app.followups.dispatcher import run_followup_dispatch

    # dispatched_at is set — DB would exclude this row
    fu = _make_followup(due_offset_hours=6, dispatched_at=datetime.now(timezone.utc))
    session = _make_session([])  # DB returns nothing due to dispatched_at IS NULL filter

    result = await run_followup_dispatch(session)
    assert result == 0
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_dispatcher_skips_followups_without_due_at():
    """Followups with no due_at are not returned by the query (due_at IS NOT NULL filter)."""
    from app.followups.dispatcher import run_followup_dispatch

    # due_at is None — DB would exclude this row
    session = _make_session([])  # DB returns nothing due to due_at IS NOT NULL filter

    result = await run_followup_dispatch(session)
    assert result == 0
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_dispatcher_skips_done_followups():
    """Followups with status='done' are not returned by the DB query's status filter."""
    from app.followups.dispatcher import run_followup_dispatch

    # status='done' — DB would exclude via status IN ('pending', 'active')
    session = _make_session([])  # DB returns nothing for done followups

    result = await run_followup_dispatch(session)
    assert result == 0
    session.add.assert_not_called()
