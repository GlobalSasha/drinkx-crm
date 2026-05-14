"""Tests for app.inbox.matcher and app.inbox.processor — Sprint 2.0 G3.

Mock-only: SQLAlchemy stubbed at import time, sessions are AsyncMock,
no Postgres / no network. Mirrors the test_audit.py / test_notifications.py
harness pattern.
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

import app.inbox.matcher as matcher_mod  # noqa: E402
import app.inbox.processor as processor_mod  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    return db


def _result(*, first=None, scalar=None, all_=None):
    """Build a faux SQLAlchemy Result. Each method gets its own MagicMock."""
    r = MagicMock()
    r.first = MagicMock(return_value=first)
    r.scalar_one_or_none = MagicMock(return_value=scalar)
    r.all = MagicMock(return_value=all_ or [])
    return r


WS = uuid.uuid4()


# ===========================================================================
# Matcher
# ===========================================================================

@pytest.mark.asyncio
async def test_matcher_finds_contact_by_exact_email():
    """Step 1 hits: contact.email == from_email → confidence 1.0."""
    db = _make_db()
    lead_id = uuid.uuid4()
    db.execute.side_effect = [_result(first=(lead_id, WS))]

    result = await matcher_mod.match_email(
        db,
        from_email="alice@acme.example",
        to_emails=["sales@drinkx.tech"],
        workspace_id=WS,
    )
    assert result.lead_id == lead_id
    assert result.confidence == 1.0
    assert result.match_type == "contact_email"
    assert result.auto_attach is True


@pytest.mark.asyncio
async def test_matcher_finds_lead_by_exact_email():
    """Step 1 misses (contact), step 2 hits (lead.email) → confidence 0.95."""
    db = _make_db()
    lead_id = uuid.uuid4()
    db.execute.side_effect = [
        _result(first=None),               # contact lookup misses
        _result(scalar=lead_id),           # lead.email lookup hits
    ]

    result = await matcher_mod.match_email(
        db,
        from_email="info@acme.example",
        to_emails=[],
        workspace_id=WS,
    )
    assert result.lead_id == lead_id
    assert result.confidence == 0.95
    assert result.match_type == "lead_email"
    assert result.auto_attach is True


@pytest.mark.asyncio
async def test_matcher_finds_lead_by_domain_unique_match():
    """Steps 1+2 miss; domain query returns exactly one lead → confidence 0.7."""
    db = _make_db()
    lead_id = uuid.uuid4()
    db.execute.side_effect = [
        _result(first=None),
        _result(scalar=None),
        _result(all_=[(lead_id,)]),
    ]

    result = await matcher_mod.match_email(
        db,
        from_email="bob@acme.example",
        to_emails=[],
        workspace_id=WS,
    )
    assert result.lead_id == lead_id
    assert result.confidence == 0.7
    assert result.match_type == "domain"
    assert result.auto_attach is False  # 0.7 < 0.8 threshold


@pytest.mark.asyncio
async def test_matcher_skips_domain_when_ambiguous():
    """Domain query returns >1 lead → matcher refuses to guess (none)."""
    db = _make_db()
    db.execute.side_effect = [
        _result(first=None),
        _result(scalar=None),
        _result(all_=[(uuid.uuid4(),), (uuid.uuid4(),)]),
    ]

    result = await matcher_mod.match_email(
        db,
        from_email="bob@acme.example",
        to_emails=[],
        workspace_id=WS,
    )
    assert result.lead_id is None
    assert result.confidence == 0.0
    assert result.match_type == "none"


@pytest.mark.asyncio
async def test_matcher_returns_none_for_unknown():
    """No contact, no lead.email, no domain match (or generic domain) → none."""
    db = _make_db()
    db.execute.side_effect = [
        _result(first=None),
        _result(scalar=None),
        # third call should NOT happen for gmail.com (generic), but be safe:
        _result(all_=[]),
    ]

    result = await matcher_mod.match_email(
        db,
        from_email="random@gmail.com",
        to_emails=[],
        workspace_id=WS,
    )
    assert result.lead_id is None
    assert result.confidence == 0.0
    assert result.match_type == "none"


# ===========================================================================
# Processor
# ===========================================================================

def _gmail_message(
    *,
    msg_id="m1",
    from_addr="alice@acme.example",
    to_addr="me@drinkx.tech",
    subject="Hi",
    snippet="hello",
    sent: bool = False,
) -> dict:
    return {
        "id": msg_id,
        "labelIds": ["SENT"] if sent else ["INBOX"],
        "snippet": snippet,
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": from_addr},
                {"name": "To", "value": to_addr},
                {"name": "Subject", "value": subject},
                {"name": "Date", "value": "Mon, 5 May 2026 10:00:00 +0000"},
            ],
            "body": {},
        },
    }


@pytest.mark.asyncio
async def test_processor_deduplicates_by_gmail_message_id():
    """If _already_processed returns True, processor returns False without
    touching the matcher, the session, or queueing tasks."""
    db = _make_db()

    with patch.object(
        processor_mod, "_already_processed", new=AsyncMock(return_value=True)
    ) as dedup, patch.object(
        processor_mod, "match_email", new=AsyncMock()
    ) as match_mock:
        out = await processor_mod.process_message(
            db,
            raw_message=_gmail_message(msg_id="dup-1"),
            user_id=uuid.uuid4(),
            workspace_id=WS,
        )

    assert out is False
    dedup.assert_awaited_once()
    match_mock.assert_not_called()
    db.add.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_processor_creates_activity_on_high_confidence_match():
    """confidence >= 0.8 → an Activity row is added with the matched lead_id
    and gmail_message_id; no InboxItem is created."""
    db = _make_db()
    lead_id = uuid.uuid4()
    user_id = uuid.uuid4()

    fake_match = matcher_mod.MatchResult(
        lead_id=lead_id, confidence=1.0, match_type="contact_email"
    )
    activity_calls: list[dict] = []
    inbox_item_calls: list[dict] = []

    class _ActivitySpy:
        def __init__(self, **kw):
            activity_calls.append(kw)

    class _InboxItemSpy:
        def __init__(self, **kw):
            inbox_item_calls.append(kw)

    with patch.object(processor_mod, "_already_processed", new=AsyncMock(return_value=False)), \
         patch.object(processor_mod, "match_email", new=AsyncMock(return_value=fake_match)), \
         patch.object(processor_mod, "Activity", _ActivitySpy), \
         patch.object(processor_mod, "InboxItem", _InboxItemSpy):
        out = await processor_mod.process_message(
            db,
            raw_message=_gmail_message(msg_id="g-100"),
            user_id=user_id,
            workspace_id=WS,
        )

    assert out is True
    assert len(activity_calls) == 1
    assert len(inbox_item_calls) == 0
    kw = activity_calls[0]
    assert kw["lead_id"] == lead_id
    assert kw["user_id"] == user_id  # ADR-019: audit trail, not visibility
    assert kw["type"] == "email"
    assert kw["channel"] == "gmail"
    assert kw["gmail_message_id"] == "g-100"
    assert kw["from_identifier"] == "alice@acme.example"
    db.add.assert_called_once()
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_processor_creates_inbox_item_on_no_match():
    """No match (or low confidence) → InboxItem with status='pending';
    no Activity row; AI suggestion task is dispatched (best-effort)."""
    db = _make_db()
    no_match = matcher_mod.MatchResult(
        lead_id=None, confidence=0.0, match_type="none"
    )

    activity_calls: list[dict] = []
    inbox_item_calls: list[dict] = []
    fake_item = MagicMock()
    fake_item.id = uuid.uuid4()

    class _ActivitySpy:
        def __init__(self, **kw):
            activity_calls.append(kw)

    def _inbox_factory(**kw):
        inbox_item_calls.append(kw)
        return fake_item

    fake_celery = MagicMock()
    fake_celery.send_task = MagicMock()
    celery_module = ModuleType("app.scheduled.celery_app")
    celery_module.celery_app = fake_celery

    with patch.object(processor_mod, "_already_processed", new=AsyncMock(return_value=False)), \
         patch.object(processor_mod, "_company_domain_match", new=AsyncMock(return_value=False)), \
         patch.object(processor_mod, "_contact_email_match", new=AsyncMock(return_value=False)), \
         patch.object(processor_mod, "match_email", new=AsyncMock(return_value=no_match)), \
         patch.object(processor_mod, "Activity", _ActivitySpy), \
         patch.object(processor_mod, "InboxItem", _inbox_factory), \
         patch.dict(sys.modules, {"app.scheduled.celery_app": celery_module}):
        out = await processor_mod.process_message(
            db,
            raw_message=_gmail_message(msg_id="g-200", from_addr="hello@unknown.example"),
            user_id=None,  # workspace-level conn → user_id is None
            workspace_id=WS,
        )

    assert out is True
    assert len(inbox_item_calls) == 1
    assert len(activity_calls) == 0
    kw = inbox_item_calls[0]
    assert kw["workspace_id"] == WS
    assert kw["user_id"] is None
    assert kw["gmail_message_id"] == "g-200"
    assert kw["from_email"] == "hello@unknown.example"
    assert kw["status"] == "pending"
    fake_celery.send_task.assert_called_once()
    args, kwargs = fake_celery.send_task.call_args
    assert args[0] == "app.scheduled.jobs.generate_inbox_suggestion"
    assert kwargs["args"] == [str(fake_item.id)]


@pytest.mark.asyncio
async def test_processor_returns_false_on_exception():
    """Any unhandled exception in the body is caught — process_message
    returns False and rolls the session back."""
    db = _make_db()

    with patch.object(
        processor_mod, "_already_processed", new=AsyncMock(side_effect=RuntimeError("boom"))
    ):
        out = await processor_mod.process_message(
            db,
            raw_message=_gmail_message(msg_id="g-err"),
            user_id=uuid.uuid4(),
            workspace_id=WS,
        )

    assert out is False
    db.rollback.assert_awaited()
