"""Tests for app.inbox.services — Sprint 2.0 G7.

Mock-only: SQLAlchemy stubbed at import time, sessions are AsyncMock,
no Postgres / no network. Mirrors the test_inbox_matcher.py harness.
"""
from __future__ import annotations

import sys
import uuid
from types import ModuleType
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Stub sqlalchemy before any ORM imports
# ---------------------------------------------------------------------------

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

import app.inbox.services as svc_mod  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

WS = uuid.uuid4()


def _make_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    return db


def _make_inbox_item(*, workspace_id=WS, user_id=None, from_email="alice@acme.example"):
    item = MagicMock()
    item.id = uuid.uuid4()
    item.workspace_id = workspace_id
    item.user_id = user_id
    item.gmail_message_id = f"g-{item.id.hex[:8]}"
    item.from_email = from_email
    item.to_emails = ["sales@drinkx.tech"]
    item.subject = "Re: пилот"
    item.body_preview = "Подтверждаем готовность"
    item.received_at = datetime(2026, 5, 7, 10, 0, tzinfo=timezone.utc)
    item.direction = "inbound"
    item.status = "pending"
    item.suggested_action = None
    return item


def _result(*, scalar=None):
    r = MagicMock()
    r.scalar_one_or_none = MagicMock(return_value=scalar)
    return r


# ===========================================================================
# 1. confirm match_lead
# ===========================================================================

@pytest.mark.asyncio
async def test_confirm_match_lead_creates_activity():
    """match_lead path: Activity row added with the matched lead_id,
    item.status flips to 'matched', audit.log gets action='inbox.match_lead'."""
    db = _make_db()
    item = _make_inbox_item()
    lead_id = uuid.uuid4()
    user_id = uuid.uuid4()

    # 1st execute → load item; 2nd execute → verify lead in workspace
    db.execute.side_effect = [
        _result(scalar=item),
        _result(scalar=lead_id),
    ]

    activity_calls: list[dict] = []

    class _ActivitySpy:
        def __init__(self, **kw):
            activity_calls.append(kw)

    audit_mock = AsyncMock()

    with patch.object(svc_mod, "Activity", _ActivitySpy), \
         patch.object(svc_mod, "audit_log", audit_mock):
        out = await svc_mod.confirm_item(
            db,
            item_id=item.id,
            user_id=user_id,
            workspace_id=WS,
            action="match_lead",
            lead_id=lead_id,
        )

    assert out is item
    assert item.status == "matched"
    assert len(activity_calls) == 1
    kw = activity_calls[0]
    assert kw["lead_id"] == lead_id
    assert kw["user_id"] == user_id  # ADR-019: audit trail
    assert kw["type"] == "email"
    assert kw["channel"] == "gmail"
    assert kw["gmail_message_id"] == item.gmail_message_id

    audit_mock.assert_awaited_once()
    audit_kwargs = audit_mock.await_args.kwargs
    assert audit_kwargs["action"] == "inbox.match_lead"
    assert audit_kwargs["entity_type"] == "inbox_item"
    assert audit_kwargs["entity_id"] == item.id
    db.commit.assert_awaited()


# ===========================================================================
# 2. confirm create_lead
# ===========================================================================

@pytest.mark.asyncio
async def test_confirm_create_lead_creates_lead_and_activity():
    """create_lead: new Lead is built with the supplied company_name,
    Activity is added attached to the new lead, item.status='created_lead'."""
    db = _make_db()
    item = _make_inbox_item()
    user_id = uuid.uuid4()

    db.execute.side_effect = [_result(scalar=item)]

    lead_calls: list[dict] = []
    activity_calls: list[dict] = []
    new_lead_id = uuid.uuid4()

    class _LeadSpy:
        def __init__(self, **kw):
            lead_calls.append(kw)
            self.id = new_lead_id
            self.company_name = kw.get("company_name")

    class _ActivitySpy:
        def __init__(self, **kw):
            activity_calls.append(kw)

    fake_pipelines_repo = MagicMock()
    fake_pipelines_repo.get_default_first_stage = AsyncMock(
        return_value=(uuid.uuid4(), uuid.uuid4())
    )
    pipelines_module = ModuleType("app.pipelines")
    repos_module = ModuleType("app.pipelines.repositories")
    repos_module.get_default_first_stage = fake_pipelines_repo.get_default_first_stage
    pipelines_module.repositories = repos_module

    audit_mock = AsyncMock()

    with patch.object(svc_mod, "Lead", _LeadSpy), \
         patch.object(svc_mod, "Activity", _ActivitySpy), \
         patch.object(svc_mod, "audit_log", audit_mock), \
         patch.dict(sys.modules, {
             "app.pipelines": pipelines_module,
             "app.pipelines.repositories": repos_module,
         }):
        out = await svc_mod.confirm_item(
            db,
            item_id=item.id,
            user_id=user_id,
            workspace_id=WS,
            action="create_lead",
            company_name="Stars Coffee",
        )

    assert out is item
    assert item.status == "created_lead"
    assert len(lead_calls) == 1
    assert lead_calls[0]["company_name"] == "Stars Coffee"
    assert lead_calls[0]["workspace_id"] == WS
    assert lead_calls[0]["assignment_status"] == "pool"
    assert lead_calls[0]["source"] == "inbox:gmail"

    assert len(activity_calls) == 1
    assert activity_calls[0]["lead_id"] == new_lead_id

    audit_mock.assert_awaited_once()
    audit_kwargs = audit_mock.await_args.kwargs
    assert audit_kwargs["action"] == "inbox.create_lead"
    assert audit_kwargs["delta"]["company_name"] == "Stars Coffee"


# ===========================================================================
# 3. create_lead falls back to from_email when company_name is empty
# ===========================================================================

@pytest.mark.asyncio
async def test_confirm_create_lead_falls_back_to_from_email():
    """company_name=None → Lead.company_name = item.from_email."""
    db = _make_db()
    item = _make_inbox_item(from_email="hello@unknown.example")
    db.execute.side_effect = [_result(scalar=item)]

    lead_calls: list[dict] = []

    class _LeadSpy:
        def __init__(self, **kw):
            lead_calls.append(kw)
            self.id = uuid.uuid4()
            self.company_name = kw.get("company_name")

    class _ActivitySpy:
        def __init__(self, **kw): pass

    fake_pipelines_repo = MagicMock()
    fake_pipelines_repo.get_default_first_stage = AsyncMock(return_value=None)
    pipelines_module = ModuleType("app.pipelines")
    repos_module = ModuleType("app.pipelines.repositories")
    repos_module.get_default_first_stage = fake_pipelines_repo.get_default_first_stage
    pipelines_module.repositories = repos_module

    with patch.object(svc_mod, "Lead", _LeadSpy), \
         patch.object(svc_mod, "Activity", _ActivitySpy), \
         patch.object(svc_mod, "audit_log", AsyncMock()), \
         patch.dict(sys.modules, {
             "app.pipelines": pipelines_module,
             "app.pipelines.repositories": repos_module,
         }):
        await svc_mod.confirm_item(
            db,
            item_id=item.id,
            user_id=uuid.uuid4(),
            workspace_id=WS,
            action="create_lead",
            company_name=None,
        )

    assert lead_calls[0]["company_name"] == "hello@unknown.example"


# ===========================================================================
# 4. confirm add_contact
# ===========================================================================

@pytest.mark.asyncio
async def test_confirm_add_contact_creates_contact():
    """add_contact: Contact row staged with email=item.from_email and
    name=contact_name; Activity also created on the same lead."""
    db = _make_db()
    item = _make_inbox_item(from_email="ivan@acme.example")
    lead_id = uuid.uuid4()
    db.execute.side_effect = [
        _result(scalar=item),       # load item
        _result(scalar=lead_id),    # verify lead in workspace
    ]

    contact_calls: list[dict] = []
    activity_calls: list[dict] = []

    class _ContactSpy:
        def __init__(self, **kw):
            contact_calls.append(kw)
            for k, v in kw.items():
                setattr(self, k, v)

    class _ActivitySpy:
        def __init__(self, **kw):
            activity_calls.append(kw)

    with patch.object(svc_mod, "Contact", _ContactSpy), \
         patch.object(svc_mod, "Activity", _ActivitySpy), \
         patch.object(svc_mod, "audit_log", AsyncMock()):
        await svc_mod.confirm_item(
            db,
            item_id=item.id,
            user_id=uuid.uuid4(),
            workspace_id=WS,
            action="add_contact",
            lead_id=lead_id,
            contact_name="Иван",
        )

    assert len(contact_calls) == 1
    assert contact_calls[0]["lead_id"] == lead_id
    assert contact_calls[0]["email"] == "ivan@acme.example"
    assert contact_calls[0]["name"] == "Иван"
    assert contact_calls[0]["source"] == "gmail"
    assert len(activity_calls) == 1
    assert activity_calls[0]["lead_id"] == lead_id


# ===========================================================================
# 5. dismiss
# ===========================================================================

@pytest.mark.asyncio
async def test_dismiss_sets_status():
    """dismiss flips status to 'dismissed' and emits action='inbox.dismiss'."""
    db = _make_db()
    item = _make_inbox_item()
    db.execute.side_effect = [_result(scalar=item)]

    audit_mock = AsyncMock()

    with patch.object(svc_mod, "audit_log", audit_mock):
        out = await svc_mod.dismiss_item(
            db,
            item_id=item.id,
            user_id=uuid.uuid4(),
            workspace_id=WS,
        )

    assert out is item
    assert item.status == "dismissed"
    audit_mock.assert_awaited_once()
    assert audit_mock.await_args.kwargs["action"] == "inbox.dismiss"
    db.commit.assert_awaited()


# ===========================================================================
# 6. cross-workspace lookup → InboxItemNotFound
# ===========================================================================

@pytest.mark.asyncio
async def test_confirm_raises_404_for_wrong_workspace():
    """If the InboxItem isn't in the caller's workspace, the load query
    returns None and the service raises InboxItemNotFound (which the
    router maps to HTTP 404)."""
    db = _make_db()
    db.execute.side_effect = [_result(scalar=None)]

    with pytest.raises(svc_mod.InboxItemNotFound):
        await svc_mod.confirm_item(
            db,
            item_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            workspace_id=WS,
            action="match_lead",
            lead_id=uuid.uuid4(),
        )

    # No activity / lead / contact / audit work happened — the early raise
    # short-circuits the whole flow.
    db.add.assert_not_called()
    db.commit.assert_not_called()
