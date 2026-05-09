"""Tests for the invite accept-flow — Sprint 2.5 G4.

Mock-only — same sqlalchemy stub pattern as test_users_service.py.
Exercises `_apply_pending_invite` directly (the unit of behaviour
G4 introduces); the parent `upsert_user_from_token` wiring is
trivial — it just calls the helper at two known points.
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

from app.auth import services as auth_svc  # noqa: E402

WS = uuid.uuid4()
INVITER_ID = uuid.uuid4()


def _make_user(*, name="Newhire User", email="newhire@drinkx.tech"):
    u = MagicMock()
    u.id = uuid.uuid4()
    u.workspace_id = WS
    u.email = email
    u.name = name
    return u


def _make_invite(*, accepted=False, inviter_id=INVITER_ID):
    inv = MagicMock()
    inv.id = uuid.uuid4()
    inv.workspace_id = WS
    inv.email = "newhire@drinkx.tech"
    inv.invited_by_user_id = inviter_id
    inv.accepted_at = None if not accepted else "2026-05-09T00:00:00Z"
    return inv


def _patch_invite_lookup(invite, db):
    """Make `db.execute(...).scalar_one_or_none()` return `invite`."""
    res = MagicMock()
    res.scalar_one_or_none = MagicMock(return_value=invite)
    db.execute = AsyncMock(return_value=res)


# ===========================================================================
# 1. Happy path: pending invite → accepted_at written + safe_notify called
# ===========================================================================

@pytest.mark.asyncio
async def test_apply_pending_invite_marks_accepted_and_notifies():
    """First sign-in matches a UserInvite row with accepted_at=NULL.
    The helper flips the timestamp + fires `safe_notify(invite_accepted)`
    targeted at the inviter. Both happen in the caller's session;
    no separate flush — same transaction as the user upsert."""
    db = AsyncMock()
    user = _make_user(name="Newhire User")
    invite = _make_invite(accepted=False)
    _patch_invite_lookup(invite, db)

    notify_calls: list[dict] = []

    async def fake_safe_notify(_db, **kwargs):
        notify_calls.append(kwargs)
        return MagicMock()

    with patch.object(auth_svc, "safe_notify", new=fake_safe_notify):
        await auth_svc._apply_pending_invite(db, user=user)

    # accepted_at flipped to a non-None datetime
    assert invite.accepted_at is not None
    # safe_notify fired exactly once at the inviter
    assert len(notify_calls) == 1
    payload = notify_calls[0]
    assert payload["kind"] == "invite_accepted"
    assert payload["workspace_id"] == WS
    assert payload["user_id"] == INVITER_ID
    assert "Newhire User" in payload["body"]
    assert payload["lead_id"] is None


# ===========================================================================
# 2. No invite row → no-op, safe_notify never called
# ===========================================================================

@pytest.mark.asyncio
async def test_apply_pending_invite_no_invite_is_noop():
    """Direct sign-up path (no admin sent an invite for this email).
    The lookup returns None — helper exits silently without touching
    any session state. Critical: the regular upsert path must keep
    working for organic Google-OAuth signups, not just invitees."""
    db = AsyncMock()
    user = _make_user()
    _patch_invite_lookup(None, db)

    notify_calls: list[dict] = []

    async def fake_safe_notify(_db, **kwargs):
        notify_calls.append(kwargs)
        return MagicMock()

    with patch.object(auth_svc, "safe_notify", new=fake_safe_notify):
        await auth_svc._apply_pending_invite(db, user=user)

    assert len(notify_calls) == 0


# ===========================================================================
# 3. Dedup-window suppression bubbles back as None — never raises
# ===========================================================================

@pytest.mark.asyncio
async def test_apply_pending_invite_swallows_dedup_window_skip():
    """If the inviter already received an `invite_accepted` ping in
    the last hour (G2 dedup window), `safe_notify` returns None
    instead of an exception. The accept-flow must NOT crash on this
    path — `accepted_at` write still happens, the inviter just
    misses the secondary ping (consistent with the dedup contract).
    Asserts the helper completes without raising."""
    db = AsyncMock()
    user = _make_user()
    invite = _make_invite(accepted=False)
    _patch_invite_lookup(invite, db)

    async def fake_safe_notify(_db, **kwargs):
        # Mirrors the real Sprint 2.5 G2 behaviour — silently skipped.
        return None

    with patch.object(auth_svc, "safe_notify", new=fake_safe_notify):
        # Must not raise — the assertion IS the absence of an exception.
        await auth_svc._apply_pending_invite(db, user=user)

    # accepted_at still flipped — the ping skip doesn't roll back the
    # transactional state of the invite row.
    assert invite.accepted_at is not None
