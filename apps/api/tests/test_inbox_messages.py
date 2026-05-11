"""Tests for app.inbox.message_services — Sprint 3.4 G1.

Mock-only: SQLAlchemy is stubbed at import time so no Postgres / network
access is required. Mirrors the harness in test_inbox_services.py.
"""
from __future__ import annotations

import sys
import uuid
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Stub sqlalchemy before any ORM imports
# ---------------------------------------------------------------------------

def _stub_sqlalchemy() -> None:
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
        def __getitem__(self, key): return _Callable()

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

import app.inbox.message_services as msg_svc  # noqa: E402
from app.inbox.schemas import WebhookPayload  # noqa: E402

WS = uuid.uuid4()


def _make_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    return db


def _scalar_result(value):
    r = MagicMock()
    r.scalar_one_or_none = MagicMock(return_value=value)
    return r


def _rows_result(rows):
    r = MagicMock()
    r.all = MagicMock(return_value=rows)
    return r


# ===========================================================================
# 1. normalize_phone — pure utility
# ===========================================================================

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("+7 (916) 123-45-67", "9161234567"),
        ("8 916 123 45 67", "9161234567"),
        ("79161234567", "9161234567"),
        ("+1-202-555-0100", "12025550100"),  # not RU → no leading-digit strip
        ("", ""),
        (None, ""),
        ("not-a-number", ""),
    ],
)
def test_normalize_phone_variants(raw, expected):
    assert msg_svc.normalize_phone(raw) == expected


# ===========================================================================
# 2. match_lead — Telegram chat id hits tg_chat_id index
# ===========================================================================

@pytest.mark.asyncio
async def test_match_lead_by_tg_chat_id():
    """Inbound TG webhook with sender chat 123456 → matches lead.tg_chat_id."""
    db = _make_db()
    target_lead_id = uuid.uuid4()
    db.execute.side_effect = [_scalar_result(target_lead_id)]

    payload = WebhookPayload(
        channel="telegram",
        direction="inbound",
        external_id="tg_1",
        sender_id="123456",
        body="Здравствуйте",
    )

    found = await msg_svc.match_lead(db, workspace_id=WS, payload=payload)

    assert found == target_lead_id
    # Should have run exactly one query — the tg-chat-id lookup
    assert db.execute.await_count == 1


# ===========================================================================
# 3. receive — dedup by (channel, external_id)
# ===========================================================================

@pytest.mark.asyncio
async def test_receive_dedups_by_external_id():
    """Replayed webhook (same channel + external_id) returns the prior row
    and does NOT insert a new InboxMessage."""
    db = _make_db()

    prior = MagicMock()
    prior.id = uuid.uuid4()
    prior.channel = "telegram"
    prior.external_id = "tg_42"
    prior.lead_id = uuid.uuid4()

    # First (and only) execute returns the prior row
    db.execute.side_effect = [_scalar_result(prior)]

    payload = WebhookPayload(
        channel="telegram",
        direction="inbound",
        external_id="tg_42",
        sender_id="555",
        body="duplicate",
    )

    msg, created = await msg_svc.receive(
        db, workspace_id=WS, payload=payload
    )

    assert msg is prior
    assert created is False
    db.add.assert_not_called()
    db.flush.assert_not_awaited()


# ===========================================================================
# 4. receive — new message, unmatched (lead_id stays None)
# ===========================================================================

@pytest.mark.asyncio
async def test_receive_creates_unmatched_when_no_lead():
    """No prior row, no Lead hit → adds an InboxMessage with lead_id=None."""
    db = _make_db()

    # dedup lookup: nothing prior
    # match_lead for "max": one query against Lead.max_user_id → None
    # match_lead phone fallback: one query enumerating phones → no rows
    db.execute.side_effect = [
        _scalar_result(None),       # dedup
        _scalar_result(None),       # max_user_id lookup
        _rows_result([]),           # phone enumeration → empty
    ]

    added: list[object] = []
    db.add = MagicMock(side_effect=added.append)

    class _InboxMessageSpy:
        # Class-level columns referenced inside the dedup query
        channel = MagicMock()
        external_id = MagicMock()

        def __init__(self, **kw):
            for k, v in kw.items():
                setattr(self, k, v)

    payload = WebhookPayload(
        channel="max",
        direction="inbound",
        external_id="max_99",
        sender_id="user-abc",
        body="первое сообщение",
    )

    with patch.object(msg_svc, "InboxMessage", _InboxMessageSpy):
        msg, created = await msg_svc.receive(
            db, workspace_id=WS, payload=payload
        )

    assert created is True
    assert len(added) == 1
    new_row = added[0]
    assert new_row.channel == "max"
    assert new_row.direction == "inbound"
    assert new_row.external_id == "max_99"
    assert new_row.sender_id == "user-abc"
    assert new_row.lead_id is None
    db.flush.assert_awaited()
