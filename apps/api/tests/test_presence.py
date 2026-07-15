"""Presence minute tracking — DB-backed."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from tests.conftest import POSTGRES_AVAILABLE

# Register ORM model for create_all + mapper config.
from app.presence.models import PresenceMinute  # noqa: F401
from app.presence import repositories as repo

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires Postgres")


@skip_no_pg
async def test_record_ping_dedupes_same_minute(db, workspace, user):
    # Call twice in immediate succession — almost always the same wall-clock
    # minute (tiny flakiness risk at minute boundaries is acceptable here).
    # ON CONFLICT (user_id, minute) DO NOTHING should keep exactly one row.
    await repo.record_ping(db, user_id=user.id, workspace_id=workspace.id)
    await repo.record_ping(db, user_id=user.id, workspace_id=workspace.id)
    await db.flush()

    n = (
        await db.execute(
            text("SELECT count(*) FROM presence_minutes WHERE user_id = :uid"),
            {"uid": user.id},
        )
    ).scalar_one()
    assert int(n) == 1


@skip_no_pg
async def test_active_minutes_range_and_daily(db, workspace, user):
    # Insert rows with explicit timestamps so assertions don't depend on wall clock.
    day0 = datetime(2026, 7, 10, 9, 0, tzinfo=timezone.utc)
    day1 = datetime(2026, 7, 11, 10, 0, tzinfo=timezone.utc)
    outside = datetime(2026, 7, 1, 8, 0, tzinfo=timezone.utc)

    rows = [
        PresenceMinute(user_id=user.id, workspace_id=workspace.id, minute=day0),
        PresenceMinute(
            user_id=user.id, workspace_id=workspace.id, minute=day0 + timedelta(minutes=1)
        ),
        PresenceMinute(
            user_id=user.id, workspace_id=workspace.id, minute=day0 + timedelta(minutes=2)
        ),
        PresenceMinute(user_id=user.id, workspace_id=workspace.id, minute=day1),
        PresenceMinute(user_id=user.id, workspace_id=workspace.id, minute=outside),
    ]
    db.add_all(rows)
    await db.flush()

    from_ = datetime(2026, 7, 10, 0, 0, tzinfo=timezone.utc)
    to = datetime(2026, 7, 12, 0, 0, tzinfo=timezone.utc)

    counts = await repo.active_minutes_range(
        db,
        workspace_id=workspace.id,
        user_ids=[user.id],
        from_=from_,
        to=to,
    )
    assert counts[user.id] == 4  # 3 on day0 + 1 on day1; outside excluded

    daily = await repo.active_daily(
        db,
        workspace_id=workspace.id,
        user_id=user.id,
        from_=from_,
        to=to,
    )
    by_date = {str(d["date"]): d["minutes"] for d in daily}
    assert by_date["2026-07-10"] == 3
    assert by_date["2026-07-11"] == 1
    assert "2026-07-01" not in by_date

    # Empty user list guard
    assert await repo.active_minutes_range(
        db, workspace_id=workspace.id, user_ids=[], from_=from_, to=to
    ) == {}
