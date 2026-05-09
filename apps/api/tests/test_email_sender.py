"""Tests for `app.email.sender` + the `_send_template_action` wire-up
— Sprint 2.6 G1.

Two surfaces:
  - `send_email` (the new tri-state SMTP wrapper) — direct unit tests
    for the stub-mode return path. The aiosmtplib network branch is
    not exercised end-to-end here (no real SMTP in mock baseline);
    G1 smoke checklist covers it on staging.
  - `_send_template_action` integration via patches — confirms the
    routing logic for email-without-recipient, email-success, and
    non-email channels.
"""
from __future__ import annotations

import sys
import uuid
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

from app.automation_builder import services as ab_svc  # noqa: E402
from app.email import sender as email_mod  # noqa: E402


WS = uuid.uuid4()


def _make_settings(*, smtp_host=""):
    """Minimal settings stub. Stub-mode = empty smtp_host."""
    s = MagicMock()
    s.smtp_host = smtp_host
    s.smtp_port = 587
    s.smtp_user = ""
    s.smtp_password = ""
    s.smtp_from = "DrinkX <noreply@drinkx.tech>"
    return s


def _make_lead(*, email=None):
    lead = MagicMock()
    lead.id = uuid.uuid4()
    lead.workspace_id = WS
    lead.email = email
    lead.company_name = "Acme"
    lead.city = "Moscow"
    return lead


def _make_template(*, channel="email"):
    t = MagicMock()
    t.id = uuid.uuid4()
    t.workspace_id = WS
    t.name = "Welcome"
    t.channel = channel
    t.text = "Hi {{lead.company_name}}!"
    return t


def _make_automation(*, template_id):
    a = MagicMock()
    a.id = uuid.uuid4()
    a.workspace_id = WS
    a.action_type = "send_template"
    a.action_config_json = {"template_id": str(template_id)}
    return a


def _patch_template_load(template, db):
    """Make `db.execute(...).scalar_one_or_none()` return `template`."""
    res = MagicMock()
    res.scalar_one_or_none = MagicMock(return_value=template)
    db.execute = AsyncMock(return_value=res)


def _captured_payload(activity_calls: list[dict]) -> dict:
    """Pull the most recent Activity kwargs.payload_json."""
    assert activity_calls, "Activity was never instantiated"
    return activity_calls[-1].get("payload_json", {})


# ===========================================================================
# 1. send_email stub-mode → False, no SMTP call, no exception
# ===========================================================================

@pytest.mark.asyncio
async def test_send_email_stub_mode_returns_false():
    """Empty SMTP_HOST = stub mode. No network I/O — function logs
    via structlog and returns False so the caller can record
    `delivery_status='stub'`. aiosmtplib must NOT be imported in this
    branch (lazy import inside the real-send guard)."""
    settings = _make_settings(smtp_host="")

    sent = await email_mod.send_email(
        to="manager@acme.com",
        subject="Welcome",
        body="Hi Acme!",
        settings=settings,
    )

    assert sent is False


# ===========================================================================
# 2. _send_template_action — lead has no email → outbound_skipped row
# ===========================================================================

@pytest.mark.asyncio
async def test_send_template_action_skips_when_lead_has_no_email():
    """Email-channel template + lead.email is None → stage an Activity
    with `delivery_status='skipped_no_email'`. send_email is NOT
    called (the early-return guards it). The parent automation_run
    stays 'success' — missing email is a row-level skip, not a
    fan-out failure."""
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    template = _make_template(channel="email")
    lead = _make_lead(email=None)
    automation = _make_automation(template_id=template.id)
    _patch_template_load(template, db)

    activity_calls: list[dict] = []

    def fake_activity(**kw):
        activity_calls.append(kw)
        return MagicMock()

    send_calls: list[dict] = []

    async def fake_send_email(**kw):
        send_calls.append(kw)
        return True  # would-be success path — must NOT be reached

    with patch.object(ab_svc, "Activity", new=fake_activity), \
         patch("app.email.sender.send_email", new=fake_send_email):
        await ab_svc._send_template_action(
            db, automation=automation, lead=lead
        )

    # send_email never invoked
    assert len(send_calls) == 0
    # One Activity staged with the skipped marker
    payload = _captured_payload(activity_calls)
    assert payload.get("delivery_status") == "skipped_no_email"
    assert payload.get("outbound_pending") is False
    # The text + template metadata still recorded for the audit trail
    assert payload.get("template_id") == str(template.id)


# ===========================================================================
# 2b. Sprint 2.6 G1 stability fix #3 — whitespace-only email also skips
# ===========================================================================

@pytest.mark.asyncio
async def test_send_template_action_skips_whitespace_only_email():
    """Whitespace-only `lead.email` (e.g. `"   "`) used to bypass the
    `not lead.email` truthy-check and reach `aiosmtplib.send` where
    header parsing would raise. Sprint 2.6 G1 stability fix #3
    strips before checking; whitespace-only renders the same
    `skipped_no_email` Activity as None."""
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    template = _make_template(channel="email")
    lead = _make_lead(email="   ")
    automation = _make_automation(template_id=template.id)
    _patch_template_load(template, db)

    activity_calls: list[dict] = []

    def fake_activity(**kw):
        activity_calls.append(kw)
        return MagicMock()

    send_calls: list[dict] = []

    async def fake_send_email(**kw):
        send_calls.append(kw)
        return True

    with patch.object(ab_svc, "Activity", new=fake_activity), \
         patch("app.email.sender.send_email", new=fake_send_email):
        await ab_svc._send_template_action(
            db, automation=automation, lead=lead
        )

    assert len(send_calls) == 0
    payload = _captured_payload(activity_calls)
    assert payload.get("delivery_status") == "skipped_no_email"
    assert payload.get("outbound_pending") is False


# ===========================================================================
# 3. _send_template_action — email path queues dispatch, no SMTP inline
# ===========================================================================

@pytest.mark.asyncio
async def test_send_template_action_email_queues_pending_dispatch():
    """Sprint 2.6 G1 stability fix: `_send_template_action` for the
    `email` channel stages an Activity with `delivery_status='pending'`
    and queues a `PendingDispatch` on the contextvar. SMTP is NOT
    called inside the parent transaction — the post-commit drainer
    handles delivery.

    Confirms: (a) send_email is NOT invoked inside the action; (b)
    Activity payload is `pending` + `outbound_pending=True`; (c) the
    rendered template body went into the queued dispatch (so
    {{lead.company_name}} substitution ran); (d) the recipient is the
    stripped lead.email."""
    from app.automation_builder.dispatch import (
        collect_pending_email_dispatches,
    )

    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    template = _make_template(channel="email")
    lead = _make_lead(email="  ceo@acme.com  ")  # whitespace stripped
    automation = _make_automation(template_id=template.id)
    _patch_template_load(template, db)

    activity_calls: list[dict] = []
    activity_id = uuid.uuid4()

    def fake_activity(**kw):
        activity_calls.append(kw)
        m = MagicMock()
        m.id = activity_id
        return m

    send_calls: list[dict] = []

    async def fake_send_email(**kw):
        send_calls.append(kw)
        return True

    with patch.object(ab_svc, "Activity", new=fake_activity), \
         patch("app.email.sender.send_email", new=fake_send_email):
        async with collect_pending_email_dispatches() as pending:
            await ab_svc._send_template_action(
                db, automation=automation, lead=lead
            )

    # send_email NOT invoked inside the action — deferred to drainer
    assert len(send_calls) == 0
    # Exactly one PendingDispatch queued, recipient stripped
    assert len(pending) == 1
    dispatch = pending[0]
    assert dispatch.to == "ceo@acme.com"  # whitespace stripped
    assert dispatch.subject == "Welcome"
    assert "Acme" in dispatch.body  # rendered substitution
    assert dispatch.activity_id == activity_id
    # Activity row records the pending state
    payload = _captured_payload(activity_calls)
    assert payload.get("delivery_status") == "pending"
    assert payload.get("outbound_pending") is True
    assert payload.get("channel") == "email"


# ===========================================================================
# 4. _send_template_action — non-email channel keeps the Sprint 2.5 stub
# ===========================================================================

@pytest.mark.asyncio
async def test_send_template_action_tg_channel_keeps_pending_stub():
    """Telegram template → no real send (provider lands in 2.7+).
    Activity row carries `delivery_status='pending'` +
    `outbound_pending=True`. Confirms send_email is NOT called for
    non-email channels — important regression-guard since G1's
    routing logic adds an `if channel == "email"` branch."""
    db = AsyncMock()
    db.add = MagicMock()
    template = _make_template(channel="tg")
    lead = _make_lead(email="ceo@acme.com")  # email present, doesn't matter
    automation = _make_automation(template_id=template.id)
    _patch_template_load(template, db)

    activity_calls: list[dict] = []

    def fake_activity(**kw):
        activity_calls.append(kw)
        return MagicMock()

    send_calls: list[dict] = []

    async def fake_send_email(**kw):
        send_calls.append(kw)
        return True

    # `send_email` is lazy-imported inside `_send_template_action`, so
    # patch the source module — the name doesn't bind on
    # `app.automation_builder.services` at module import time.
    with patch.object(ab_svc, "Activity", new=fake_activity), \
         patch("app.email.sender.send_email", new=fake_send_email):
        await ab_svc._send_template_action(
            db, automation=automation, lead=lead
        )

    # send_email NOT called for non-email channels
    assert len(send_calls) == 0
    # Activity row stays in pending state
    payload = _captured_payload(activity_calls)
    assert payload.get("delivery_status") == "pending"
    assert payload.get("outbound_pending") is True
    assert payload.get("channel") == "tg"
