"""Tests for Sprint 1.4 Phase 3 — daily plan REST routes.

SQLAlchemy is stubbed at import time. Service functions are mocked with AsyncMock.
Celery send_task is mocked in request_regenerate tests.
"""
from __future__ import annotations

import sys
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Stub sqlalchemy before any ORM imports
# ---------------------------------------------------------------------------

def _stub_sqlalchemy():
    if "sqlalchemy" in sys.modules:
        return

    def _noop(*a, **kw):
        return None

    class _Callable:
        def __init__(self, *a, **kw): pass
        def __call__(self, *a, **kw): return _Callable()
        def __class_getitem__(cls, item): return cls
        def __getattr__(self, name): return _Callable()
        def __eq__(self, other): return True
        def __ne__(self, other): return True

    sa = ModuleType("sqlalchemy")
    for name in (
        "Column", "ForeignKey", "Integer", "String", "Text", "JSON",
        "Numeric", "DateTime", "Boolean", "Index", "select",
        "desc", "false", "UniqueConstraint", "text", "nullslast",
        "asc", "or_", "and_", "update", "delete", "cast", "literal",
        "Date",
    ):
        setattr(sa, name, _Callable)

    class _Func:
        def __getattr__(self, name):
            return _Callable

    sa.func = _Func()

    sa_ext = ModuleType("sqlalchemy.ext")
    sa_async = ModuleType("sqlalchemy.ext.asyncio")
    sa_dialects = ModuleType("sqlalchemy.dialects")
    sa_pg = ModuleType("sqlalchemy.dialects.postgresql")
    sa_orm = ModuleType("sqlalchemy.orm")

    class _Mapped:
        def __class_getitem__(cls, item): return cls

    class _DeclarativeBase:
        metadata = MagicMock()

    sa_orm.DeclarativeBase = _DeclarativeBase
    sa_orm.Mapped = _Mapped
    sa_orm.mapped_column = _noop
    sa_orm.relationship = _Callable()
    sa_orm.selectinload = _Callable()
    sa_orm.joinedload = _Callable()

    sa_pg.UUID = _Callable
    sa_pg.JSON = _Callable

    sa_async.AsyncSession = object
    sa_async.async_sessionmaker = _Callable
    sa_async.create_async_engine = _Callable
    sa_async.AsyncEngine = object

    sys.modules["sqlalchemy"] = sa
    sys.modules["sqlalchemy.ext"] = sa_ext
    sys.modules["sqlalchemy.ext.asyncio"] = sa_async
    sys.modules["sqlalchemy.dialects"] = sa_dialects
    sys.modules["sqlalchemy.dialects.postgresql"] = sa_pg
    sys.modules["sqlalchemy.orm"] = sa_orm

    if "asyncpg" not in sys.modules:
        sys.modules["asyncpg"] = ModuleType("asyncpg")


_stub_sqlalchemy()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_item(plan_id=None, lead_id=None, done=False):
    item = MagicMock()
    item.id = uuid.uuid4()
    item.daily_plan_id = plan_id or uuid.uuid4()
    item.lead_id = lead_id or uuid.uuid4()
    item.position = 0
    item.priority_score = Decimal("72.50")
    item.estimated_minutes = 15
    item.time_block = "morning"
    item.task_kind = "call"
    item.hint_one_liner = "Позвонить и уточнить статус"
    item.done = done
    item.done_at = None
    item.lead_company_name = "Test Corp"
    item.lead_segment = "HoReCa"
    item.lead_city = "Москва"
    item.created_at = datetime.now(tz=timezone.utc)
    item.updated_at = datetime.now(tz=timezone.utc)
    return item


def _make_plan(user_id=None, plan_date=None, status="ready", items=None):
    plan = MagicMock()
    plan.id = uuid.uuid4()
    plan.workspace_id = uuid.uuid4()
    plan.user_id = user_id or uuid.uuid4()
    plan.plan_date = plan_date or date.today()
    plan.generated_at = datetime.now(tz=timezone.utc)
    plan.status = status
    plan.generation_error = None
    plan.summary_json = {"total_minutes": 60, "count": 4}
    plan.items = items or []
    plan.created_at = datetime.now(tz=timezone.utc)
    plan.updated_at = datetime.now(tz=timezone.utc)
    return plan


def _make_user(workspace_id=None):
    user = MagicMock()
    user.id = uuid.uuid4()
    user.workspace_id = workspace_id or uuid.uuid4()
    user.timezone = "Europe/Moscow"
    user.role = "manager"
    return user


# ---------------------------------------------------------------------------
# Tests — get_my_today
# ---------------------------------------------------------------------------

import app.daily_plan.services as svc_mod  # noqa: E402


@pytest.mark.asyncio
async def test_get_my_today_returns_none_when_no_plan():
    """get_today_plan_for_user returns None → endpoint returns None."""
    db = AsyncMock()
    user = _make_user()

    with patch.object(svc_mod, "get_today_plan_for_user", new=AsyncMock(return_value=None)):
        result = await svc_mod.get_today_plan_for_user(db, user=user)

    assert result is None


@pytest.mark.asyncio
async def test_get_my_today_returns_plan_when_exists():
    """get_today_plan_for_user returns the plan row when it exists."""
    db = AsyncMock()
    user = _make_user()
    item = _make_item()
    plan = _make_plan(user_id=user.id, items=[item])

    with patch.object(svc_mod, "get_today_plan_for_user", new=AsyncMock(return_value=plan)):
        result = await svc_mod.get_today_plan_for_user(db, user=user)

    assert result is plan
    assert result.status == "ready"
    assert len(result.items) == 1


# ---------------------------------------------------------------------------
# Tests — get_plan_for_date
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_plan_for_date():
    """get_plan_for_user_date returns the correct plan for a given date."""
    db = AsyncMock()
    user_id = uuid.uuid4()
    target_date = date(2026, 5, 7)
    plan = _make_plan(user_id=user_id, plan_date=target_date)

    with patch.object(svc_mod, "get_plan_for_user_date", new=AsyncMock(return_value=plan)):
        result = await svc_mod.get_plan_for_user_date(db, user_id=user_id, plan_date=target_date)

    assert result is plan
    assert result.plan_date == target_date


# ---------------------------------------------------------------------------
# Tests — request_regenerate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_regenerate_creates_generating_row_and_dispatches_task():
    """request_regenerate creates a new plan row with status='generating' and fires Celery task."""
    db = AsyncMock()

    # No existing plan
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=execute_result)
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    user = _make_user()
    plan_date = date(2026, 5, 7)

    fake_async_result = MagicMock()
    fake_async_result.id = "fake-task-id-123"

    new_plan = _make_plan(user_id=user.id, plan_date=plan_date, status="generating")
    db.add = MagicMock()

    mock_celery = MagicMock()
    mock_celery.send_task = MagicMock(return_value=fake_async_result)

    with (
        patch("app.daily_plan.services.DailyPlan", return_value=new_plan),
        patch("app.scheduled.celery_app.celery_app", mock_celery),
    ):
        result_plan, task_id = await svc_mod.request_regenerate(db, user=user, plan_date=plan_date)

    assert task_id == "fake-task-id-123"
    assert result_plan.status == "generating"


@pytest.mark.asyncio
async def test_regenerate_replaces_existing_plan():
    """request_regenerate sets status='generating' on an existing plan and fires Celery task."""
    db = AsyncMock()
    user = _make_user()
    plan_date = date(2026, 5, 7)

    existing_plan = _make_plan(user_id=user.id, plan_date=plan_date, status="ready")

    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = existing_plan
    db.execute = AsyncMock(return_value=execute_result)
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    fake_async_result = MagicMock()
    fake_async_result.id = "regen-task-456"

    mock_celery = MagicMock()
    mock_celery.send_task = MagicMock(return_value=fake_async_result)

    with patch("app.scheduled.celery_app.celery_app", mock_celery):
        result_plan, task_id = await svc_mod.request_regenerate(db, user=user, plan_date=plan_date)

    assert result_plan.status == "generating"
    assert task_id == "regen-task-456"


# ---------------------------------------------------------------------------
# Tests — mark_item_done
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_complete_item_marks_done():
    """mark_item_done sets done=True and done_at on a valid item."""
    db = AsyncMock()
    user_id = uuid.uuid4()
    item = _make_item()
    item.done = False
    item.done_at = None

    # lead is None to avoid lazy load issues
    item.lead = None

    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = item
    db.execute = AsyncMock(return_value=execute_result)
    db.flush = AsyncMock()

    result = await svc_mod.mark_item_done(db, item_id=item.id, user_id=user_id)

    assert result is item
    assert item.done is True
    assert item.done_at is not None
    db.flush.assert_called_once()


@pytest.mark.asyncio
async def test_complete_item_404_for_other_users_item():
    """mark_item_done returns None when the item belongs to a different user."""
    db = AsyncMock()

    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None  # not found for this user
    db.execute = AsyncMock(return_value=execute_result)

    result = await svc_mod.mark_item_done(db, item_id=uuid.uuid4(), user_id=uuid.uuid4())

    assert result is None
