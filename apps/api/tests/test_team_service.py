"""Tests for app.team.services — Sprint 3.4 G1.

Mock-only: stubs sqlalchemy so the ORM imports don't pull in real
modules. Same pattern as tests/test_users_service.py.
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _stub_sqlalchemy():
    if "sqlalchemy" in sys.modules:
        return

    class _Callable:
        def __init__(self, *a, **kw): pass
        def __call__(self, *a, **kw): return _Callable()
        def __class_getitem__(cls, item): return cls
        def __getitem__(self, key): return _Callable()
        def __getattr__(self, name): return _Callable()
        def __eq__(self, other): return True
        def __ne__(self, other): return True

    sa = ModuleType("sqlalchemy")
    for name in (
        "Column", "ForeignKey", "Integer", "String", "Text", "JSON",
        "Numeric", "DateTime", "Boolean", "Index", "select", "func",
        "desc", "false", "true", "UniqueConstraint", "text", "nullslast",
        "nullsfirst", "asc", "or_", "and_", "update", "delete", "cast",
        "literal", "Date",
    ):
        setattr(sa, name, _Callable)

    class _Func:
        def __getattr__(self, name): return _Callable
    sa.func = _Func()

    sa_async = ModuleType("sqlalchemy.ext.asyncio")
    sa_pg = ModuleType("sqlalchemy.dialects.postgresql")
    sa_orm = ModuleType("sqlalchemy.orm")
    sa_ext = ModuleType("sqlalchemy.ext")
    sa_dialects = ModuleType("sqlalchemy.dialects")
    sa_exc = ModuleType("sqlalchemy.exc")

    class _Mapped:
        def __class_getitem__(cls, item): return cls

    class _DeclarativeBase:
        metadata = MagicMock()

    sa_orm.DeclarativeBase = _DeclarativeBase
    sa_orm.Mapped = _Mapped
    sa_orm.mapped_column = lambda *a, **kw: _Callable()
    sa_orm.relationship = _Callable()
    sa_orm.selectinload = _Callable()
    sa_orm.joinedload = _Callable()
    sa_pg.UUID = _Callable
    sa_pg.JSON = _Callable
    sa_async.AsyncSession = object
    sa_async.async_sessionmaker = _Callable
    sa_async.create_async_engine = _Callable
    sa_async.AsyncEngine = object

    class _IntegrityError(Exception):
        pass
    sa_exc.IntegrityError = _IntegrityError

    sys.modules["sqlalchemy"] = sa
    sys.modules["sqlalchemy.ext"] = sa_ext
    sys.modules["sqlalchemy.ext.asyncio"] = sa_async
    sys.modules["sqlalchemy.dialects"] = sa_dialects
    sys.modules["sqlalchemy.dialects.postgresql"] = sa_pg
    sys.modules["sqlalchemy.orm"] = sa_orm
    sys.modules["sqlalchemy.exc"] = sa_exc

    if "asyncpg" not in sys.modules:
        sys.modules["asyncpg"] = ModuleType("asyncpg")


_stub_sqlalchemy()

from app.team import services as svc  # noqa: E402


WS = uuid.uuid4()


def _make_user(*, id_=None, name="Кирилл", email="k@x.io", role="manager", last_login=None):
    u = MagicMock()
    u.id = id_ or uuid.uuid4()
    u.workspace_id = WS
    u.name = name
    u.email = email
    u.role = role
    u.last_login_at = last_login
    return u


# ---------------------------------------------------------------------------
# resolve_period
# ---------------------------------------------------------------------------

def test_resolve_period_today_returns_day_window():
    from_, to = svc.resolve_period("today")
    assert from_.hour == 0 and from_.minute == 0
    assert to.hour == 23 and to.minute == 59
    assert (to - from_).total_seconds() < 24 * 3600


def test_resolve_period_week_spans_seven_days():
    from_, to = svc.resolve_period("week")
    # 6 days + same day = ~7 day window
    assert 6 * 24 * 3600 <= (to - from_).total_seconds() <= 7 * 24 * 3600


def test_resolve_period_month_spans_thirty_days():
    from_, to = svc.resolve_period("month")
    assert 29 * 24 * 3600 <= (to - from_).total_seconds() <= 30 * 24 * 3600


def test_resolve_period_invalid_raises():
    with pytest.raises(ValueError):
        svc.resolve_period("yearly")


# ---------------------------------------------------------------------------
# team_stats — fan-out + zip
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_team_stats_zips_metrics_per_user():
    """team_stats lists users, calls the four per-user repo helpers,
    and zips the counts into one row per user. Missing entries default
    to zero (not all users have every metric)."""
    db = AsyncMock()
    u1 = _make_user(name="Алиса", email="a@x.io", role="admin")
    u2 = _make_user(name="Боря",  email="b@x.io", role="manager")

    async def fake_list_for_workspace(_db, *, workspace_id):
        return [u1, u2], 2

    async def fake_kp(_db, **kw):    return {u1.id: 3}                # u2 absent
    async def fake_taken(_db, **kw): return {u1.id: 5, u2.id: 2}
    async def fake_moved(_db, **kw): return {u2.id: 7}
    async def fake_tasks(_db, **kw): return {u1.id: 4, u2.id: 1}
    async def fake_last(_db, **kw):
        ts = datetime(2026, 5, 11, 14, 0, tzinfo=timezone.utc)
        return {u1.id: ts}

    with patch(
        "app.users.repositories.list_for_workspace", new=fake_list_for_workspace,
    ), patch(
        "app.team.repositories.kp_sent_per_user", new=fake_kp,
    ), patch(
        "app.team.repositories.leads_taken_per_user", new=fake_taken,
    ), patch(
        "app.team.repositories.leads_moved_per_user", new=fake_moved,
    ), patch(
        "app.team.repositories.tasks_completed_per_user", new=fake_tasks,
    ), patch(
        "app.team.repositories.last_active_per_user", new=fake_last,
    ):
        out = await svc.team_stats(db, workspace_id=WS, period="week")

    assert out["period"] == "week"
    assert len(out["managers"]) == 2

    by_email = {m["email"]: m for m in out["managers"]}
    assert by_email["a@x.io"]["stats"]["kp_sent"] == 3
    assert by_email["a@x.io"]["stats"]["leads_taken_from_pool"] == 5
    assert by_email["a@x.io"]["stats"]["leads_moved"] == 0   # missing → 0
    assert by_email["a@x.io"]["stats"]["tasks_completed"] == 4
    assert by_email["a@x.io"]["last_active_at"] is not None

    assert by_email["b@x.io"]["stats"]["kp_sent"] == 0       # missing → 0
    assert by_email["b@x.io"]["stats"]["leads_moved"] == 7


@pytest.mark.asyncio
async def test_team_stats_last_active_falls_back_to_last_login():
    """When the user has no activity rows, last_active_at falls back to
    User.last_login_at — the cheapest signal we have for «kind of
    active». If both are None the field is null."""
    db = AsyncMock()
    login_ts = datetime(2026, 5, 10, tzinfo=timezone.utc)
    u1 = _make_user(last_login=login_ts)
    u2 = _make_user(last_login=None)

    async def fake_list_for_workspace(_db, *, workspace_id):
        return [u1, u2], 2
    async def fake_zero(_db, **kw): return {}

    with patch(
        "app.users.repositories.list_for_workspace", new=fake_list_for_workspace,
    ), patch(
        "app.team.repositories.kp_sent_per_user", new=fake_zero,
    ), patch(
        "app.team.repositories.leads_taken_per_user", new=fake_zero,
    ), patch(
        "app.team.repositories.leads_moved_per_user", new=fake_zero,
    ), patch(
        "app.team.repositories.tasks_completed_per_user", new=fake_zero,
    ), patch(
        "app.team.repositories.last_active_per_user", new=fake_zero,
    ):
        out = await svc.team_stats(db, workspace_id=WS, period="today")

    assert out["managers"][0]["last_active_at"] == login_ts
    assert out["managers"][1]["last_active_at"] is None


# ---------------------------------------------------------------------------
# manager_stats
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_manager_stats_includes_daily_breakdown():
    db = AsyncMock()
    user = _make_user()

    async def fake_get(_db, *, user_id, workspace_id):
        assert user_id == user.id
        return user

    async def fake_one(_db, **kw): return {user.id: 2}
    async def fake_daily(_db, **kw):
        from datetime import date
        return [
            {"date": date(2026, 5, 5), "kp_sent": 0, "leads_taken_from_pool": 2, "leads_moved": 3, "tasks_completed": 1},
            {"date": date(2026, 5, 6), "kp_sent": 1, "leads_taken_from_pool": 1, "leads_moved": 2, "tasks_completed": 2},
        ]

    with patch(
        "app.users.repositories.get_by_id", new=fake_get,
    ), patch(
        "app.team.repositories.kp_sent_per_user", new=fake_one,
    ), patch(
        "app.team.repositories.leads_taken_per_user", new=fake_one,
    ), patch(
        "app.team.repositories.leads_moved_per_user", new=fake_one,
    ), patch(
        "app.team.repositories.tasks_completed_per_user", new=fake_one,
    ), patch(
        "app.team.repositories.daily_breakdown", new=fake_daily,
    ):
        out = await svc.manager_stats(
            db, workspace_id=WS, user_id=user.id, period="week"
        )

    assert out["user_id"] == user.id
    assert out["stats"]["kp_sent"] == 2
    assert out["stats"]["leads_moved"] == 2
    assert len(out["daily"]) == 2
    assert out["daily"][1]["kp_sent"] == 1


@pytest.mark.asyncio
async def test_manager_stats_404_when_user_missing():
    db = AsyncMock()

    async def fake_get(_db, *, user_id, workspace_id):
        return None

    with patch("app.users.repositories.get_by_id", new=fake_get):
        with pytest.raises(svc.UserNotFound):
            await svc.manager_stats(
                db, workspace_id=WS, user_id=uuid.uuid4(), period="week"
            )
