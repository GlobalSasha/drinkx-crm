"""Tests for the daily email digest pipeline — Sprint 1.5 group 5.

SQLAlchemy stubbed at import time. No DB, no SMTP, no asyncpg.
"""
from __future__ import annotations

import sys
import uuid
from datetime import date
from types import ModuleType, SimpleNamespace
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
        def __getitem__(self, key): return _Callable()
        def __getattr__(self, name): return _Callable()
        def __eq__(self, other): return True
        def __ne__(self, other): return True
        # Comparison operators chain the stub instead of falling back to
        # Python's default rich-comparison rules — needed for service code
        # that builds queries like `Model.timestamp < datetime.now()`.
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

import app.notifications.digest as digest_mod  # noqa: E402
import app.notifications.email_sender as sender_mod  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _settings(smtp_host: str = ""):
    return SimpleNamespace(
        smtp_host=smtp_host,
        smtp_port=587,
        smtp_user="u",
        smtp_password="p",
        smtp_from="DrinkX CRM <noreply@crm.drinkx.tech>",
    )


def _make_session(plan, plan_items, overdue, briefs):
    """Return an AsyncMock session whose `execute()` walks 4 result objects in
    the same order build_digest_for_user issues queries:
      1) plan lookup
      2) plan items (skipped if plan is None or status != ready)
      3) overdue followups
      4) yesterday's briefs
    """
    session = AsyncMock()

    plan_res = MagicMock()
    plan_res.scalar_one_or_none.return_value = plan

    items_res = MagicMock()
    items_res.all.return_value = plan_items

    overdue_res = MagicMock()
    overdue_res.all.return_value = overdue

    briefs_res = MagicMock()
    briefs_res.all.return_value = briefs

    # The digest issues plan-items query only when plan is ready.
    if plan is not None and getattr(plan, "status", None) == "ready":
        side_effect = [plan_res, items_res, overdue_res, briefs_res]
    else:
        side_effect = [plan_res, overdue_res, briefs_res]

    session.execute = AsyncMock(side_effect=side_effect)
    return session


def _plan(status: str = "ready"):
    p = MagicMock()
    p.id = uuid.uuid4()
    p.status = status
    return p


def _plan_item(position: int, company: str = "Acme"):
    item = MagicMock()
    item.id = uuid.uuid4()
    item.position = position
    item.time_block = "morning"
    item.hint_one_liner = f"Позвонить {company}"
    lead = MagicMock()
    lead.id = uuid.uuid4()
    lead.company_name = company
    return (item, lead)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stub_mode_logs_instead_of_sending():
    """SMTP_HOST="" → no aiosmtplib call, return True."""
    with (
        patch.object(sender_mod, "get_settings", return_value=_settings(smtp_host="")),
        # Make sure aiosmtplib import-then-send WOULD blow up if reached.
        patch.dict("sys.modules", {"aiosmtplib": MagicMock(send=AsyncMock(side_effect=AssertionError("must not be called")))}),
    ):
        ok = await sender_mod.send_email(
            to="me@example.com",
            subject="hi",
            html="<p>hello world</p>",
        )
    assert ok is True


@pytest.mark.asyncio
async def test_send_returns_false_on_smtp_error():
    """Real SMTP host but aiosmtplib.send raises → False, no propagation."""
    fake_aiosmtplib = MagicMock()
    fake_aiosmtplib.send = AsyncMock(side_effect=ConnectionError("relay down"))

    with (
        patch.object(sender_mod, "get_settings", return_value=_settings(smtp_host="smtp.example.com")),
        patch.dict("sys.modules", {"aiosmtplib": fake_aiosmtplib}),
    ):
        ok = await sender_mod.send_email(
            to="me@example.com",
            subject="hi",
            html="<p>hi</p>",
        )
    assert ok is False
    fake_aiosmtplib.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_digest_skips_when_no_plan_no_overdue_no_briefs():
    """All three sections empty → return False, send_email not called."""
    session = _make_session(plan=None, plan_items=[], overdue=[], briefs=[])

    fake_send = AsyncMock(return_value=True)
    with patch.object(digest_mod, "send_email", fake_send):
        sent = await digest_mod.build_digest_for_user(
            session,
            user_id=uuid.uuid4(),
            workspace_id=uuid.uuid4(),
            user_name="Sasha",
            user_email="sasha@example.com",
            today=date(2026, 5, 7),
        )
    assert sent is False
    fake_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_digest_renders_top5_plan_items():
    """Builder slices plan items at 5; the 6th must NOT appear in the HTML."""
    plan = _plan("ready")
    items = [_plan_item(i, company=f"Company-{i}") for i in range(6)]
    session = _make_session(plan=plan, plan_items=items, overdue=[], briefs=[])

    captured: dict[str, str] = {}

    async def fake_send(*, to: str, subject: str, html: str) -> bool:
        captured["html"] = html
        return True

    with patch.object(digest_mod, "send_email", fake_send):
        sent = await digest_mod.build_digest_for_user(
            session,
            user_id=uuid.uuid4(),
            workspace_id=uuid.uuid4(),
            user_name="Sasha",
            user_email="sasha@example.com",
            today=date(2026, 5, 7),
        )

    assert sent is True
    html = captured["html"]
    for i in range(5):
        assert f"Company-{i}" in html, f"missing Company-{i} in rendered HTML"
    assert "Company-5" not in html, "6th item should be sliced off (top-5 only)"


@pytest.mark.asyncio
async def test_digest_sends_when_plan_exists():
    """Two plan items + nothing else → send_email called once with `to=email`."""
    plan = _plan("ready")
    items = [_plan_item(0, "Acme"), _plan_item(1, "Beta")]
    session = _make_session(plan=plan, plan_items=items, overdue=[], briefs=[])

    fake_send = AsyncMock(return_value=True)
    with patch.object(digest_mod, "send_email", fake_send):
        sent = await digest_mod.build_digest_for_user(
            session,
            user_id=uuid.uuid4(),
            workspace_id=uuid.uuid4(),
            user_name="Sasha",
            user_email="sasha@example.com",
            today=date(2026, 5, 7),
        )

    assert sent is True
    fake_send.assert_awaited_once()
    kwargs = fake_send.await_args.kwargs
    assert kwargs["to"] == "sasha@example.com"
    assert "07.05.2026" in kwargs["subject"]
    assert "Acme" in kwargs["html"]
    assert "Beta" in kwargs["html"]
