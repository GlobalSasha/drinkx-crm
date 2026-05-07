"""Tests for app.notifications — Sprint 1.5 group 1.

SQLAlchemy is stubbed at import time (same pattern as
test_enrichment_routes.py / test_daily_plan_routes.py). Service
functions are tested with AsyncMock DB sessions — no Postgres needed.
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
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
        """Stub returning itself from any call/attr — supports chaining."""
        def __init__(self, *a, **kw): pass
        def __call__(self, *a, **kw): return _Callable()
        def __class_getitem__(cls, item): return cls
        def __getattr__(self, name): return _Callable()
        def __eq__(self, other): return True
        def __ne__(self, other): return True
        def __lt__(self, other): return _Callable()
        def __le__(self, other): return _Callable()
        def __gt__(self, other): return _Callable()
        def __ge__(self, other): return _Callable()

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
    # Important: return a chainable stub (not None) so service-level code that
    # touches `Model.column.is_(...)` / `.in_(...)` keeps working under the
    # stub. mapped_column is invoked at class-creation time per column.
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
# Imports after stubbing
# ---------------------------------------------------------------------------

import app.notifications.services as svc_mod  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db():
    """AsyncMock session with the methods notify/list/mark_* call."""
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock()
    return db


def _captured_notification_kwargs(MockNotification: MagicMock) -> dict:
    """Return kwargs the Notification constructor was called with."""
    assert MockNotification.call_args is not None, "Notification was never constructed"
    return dict(MockNotification.call_args.kwargs)


# ---------------------------------------------------------------------------
# notify() — staging shape
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_notify_stages_row_with_supplied_fields():
    """notify() builds a Notification with the kwargs supplied, db.add + flush called."""
    db = _make_db()
    workspace_id = uuid.uuid4()
    user_id = uuid.uuid4()
    lead_id = uuid.uuid4()

    fake_row = MagicMock()
    with patch.object(svc_mod, "Notification", return_value=fake_row) as MockNotification:
        result = await svc_mod.notify(
            db,
            workspace_id=workspace_id,
            user_id=user_id,
            kind="lead_transferred",
            title="Передан лид: Acme",
            body="hello",
            lead_id=lead_id,
        )

    assert result is fake_row
    kwargs = _captured_notification_kwargs(MockNotification)
    assert kwargs["workspace_id"] == workspace_id
    assert kwargs["user_id"] == user_id
    assert kwargs["kind"] == "lead_transferred"
    assert kwargs["title"] == "Передан лид: Acme"
    assert kwargs["body"] == "hello"
    assert kwargs["lead_id"] == lead_id
    db.add.assert_called_once_with(fake_row)
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_notify_truncates_long_title_to_200_chars():
    """Titles >200 chars are truncated by notify() before they reach the model."""
    db = _make_db()
    long_title = "A" * 500

    with patch.object(svc_mod, "Notification") as MockNotification:
        MockNotification.return_value = MagicMock()
        await svc_mod.notify(
            db,
            workspace_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            kind="system",
            title=long_title,
        )

    kwargs = _captured_notification_kwargs(MockNotification)
    assert len(kwargs["title"]) == 200


@pytest.mark.asyncio
async def test_notify_normalizes_falsy_body_to_empty_string():
    """`body=None` (or any falsy) becomes '' so the NOT NULL column is satisfied."""
    db = _make_db()

    with patch.object(svc_mod, "Notification") as MockNotification:
        MockNotification.return_value = MagicMock()
        await svc_mod.notify(
            db,
            workspace_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            kind="system",
            title="t",
            body="",
        )

    assert _captured_notification_kwargs(MockNotification)["body"] == ""


# ---------------------------------------------------------------------------
# safe_notify() — never raises
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_safe_notify_swallows_exceptions_and_returns_none():
    """Failures in notify() must NOT bubble out of safe_notify."""
    db = _make_db()

    with patch.object(svc_mod, "notify", new=AsyncMock(side_effect=RuntimeError("boom"))):
        result = await svc_mod.safe_notify(
            db,
            workspace_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            kind="system",
            title="t",
        )

    assert result is None


# ---------------------------------------------------------------------------
# mark_read() — cross-user guard
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mark_read_returns_none_for_other_users_row():
    """mark_read returns None when the WHERE filter (user_id) doesn't match —
    i.e. the row exists but belongs to another user."""
    db = _make_db()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=execute_result)

    result = await svc_mod.mark_read(
        db,
        notification_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
    )

    assert result is None
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_mark_read_stamps_read_at_when_unread():
    """An owned, unread row gets read_at = now() and is flushed."""
    db = _make_db()

    row = MagicMock()
    row.read_at = None
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = row
    db.execute = AsyncMock(return_value=execute_result)

    result = await svc_mod.mark_read(
        db,
        notification_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
    )

    assert result is row
    assert isinstance(row.read_at, datetime)
    assert row.read_at.tzinfo is not None
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_mark_read_idempotent_when_already_read():
    """If read_at is already set, mark_read returns the row but does NOT flush
    (no-op write)."""
    db = _make_db()

    earlier = datetime(2026, 1, 1, tzinfo=timezone.utc)
    row = MagicMock()
    row.read_at = earlier
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = row
    db.execute = AsyncMock(return_value=execute_result)

    result = await svc_mod.mark_read(
        db,
        notification_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
    )

    assert result is row
    assert row.read_at == earlier
    db.flush.assert_not_awaited()


# ---------------------------------------------------------------------------
# mark_all_read() — affected count + scoping
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mark_all_read_returns_rowcount():
    """mark_all_read returns the UPDATE rowcount as an int."""
    db = _make_db()
    execute_result = MagicMock()
    execute_result.rowcount = 4
    db.execute = AsyncMock(return_value=execute_result)

    affected = await svc_mod.mark_all_read(db, user_id=uuid.uuid4())

    assert affected == 4
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_mark_all_read_handles_null_rowcount():
    """rowcount may be None on some drivers; service coerces to 0."""
    db = _make_db()
    execute_result = MagicMock()
    execute_result.rowcount = None
    db.execute = AsyncMock(return_value=execute_result)

    affected = await svc_mod.mark_all_read(db, user_id=uuid.uuid4())
    assert affected == 0


# ---------------------------------------------------------------------------
# list_for_user() — returns (items, total, unread_count)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_for_user_returns_three_part_tuple():
    """list_for_user issues 3 SELECTs and packs them into (items, total, unread)."""
    db = _make_db()

    item_a = MagicMock()
    item_b = MagicMock()
    items_result = MagicMock()
    items_result.scalars.return_value = MagicMock(all=lambda: [item_a, item_b])

    total_result = MagicMock()
    total_result.scalar_one.return_value = 5

    unread_result = MagicMock()
    unread_result.scalar_one.return_value = 2

    db.execute = AsyncMock(side_effect=[total_result, unread_result, items_result])

    items, total, unread = await svc_mod.list_for_user(db, user_id=uuid.uuid4())

    assert items == [item_a, item_b]
    assert total == 5
    assert unread == 2
    assert db.execute.await_count == 3
