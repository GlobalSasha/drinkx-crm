"""Tests for app.users.services + the diff_engine carryover —
Sprint 2.4 G1.

Mock-only: stubs sqlalchemy at import time so the ORM imports don't
drag the real declarative base in. Same pattern as
tests/test_pipelines_service.py + tests/test_auth_bootstrap.py.
"""
from __future__ import annotations

import sys
import uuid
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# sqlalchemy stub
# ---------------------------------------------------------------------------

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
        "nullsfirst",
        "asc", "or_", "and_", "update", "delete", "cast", "literal",
        "Date",
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

from app.users import services as svc  # noqa: E402

WS = uuid.uuid4()
ADMIN_ID = uuid.uuid4()


def _make_user(*, id_=None, email="x@y.io", role="manager"):
    u = MagicMock()
    u.id = id_ or uuid.uuid4()
    u.workspace_id = WS
    u.email = email
    u.role = role
    u.name = "Test User"
    return u


# ===========================================================================
# 1. invite_user happy path
# ===========================================================================

@pytest.mark.asyncio
async def test_invite_user_persists_and_sends_email():
    """invite_user calls the Supabase admin API to send a magic-link
    AND inserts a UserInvite row. Both happen — neither is sufficient
    on its own."""
    db = AsyncMock()

    invite_calls: list[dict] = []
    create_calls: list[dict] = []

    async def fake_get_invite_by_email(_session, **kwargs):
        return None  # no existing invite

    async def fake_create_invite(_session, **kwargs):
        create_calls.append(kwargs)
        out = MagicMock()
        out.id = uuid.uuid4()
        for k, v in kwargs.items():
            setattr(out, k, v)
        return out

    async def fake_send(*, email):
        invite_calls.append({"email": email})

    with patch(
        "app.users.repositories.get_invite_by_email",
        new=fake_get_invite_by_email,
    ), patch(
        "app.users.repositories.create_invite",
        new=fake_create_invite,
    ), patch(
        "app.users.services.send_invite_email",
        new=fake_send,
    ):
        result = await svc.invite_user(
            db,
            workspace_id=WS,
            invited_by_user_id=ADMIN_ID,
            email="newhire@drinkx.tech",
            role="manager",
        )

    assert len(invite_calls) == 1
    assert invite_calls[0]["email"] == "newhire@drinkx.tech"
    assert len(create_calls) == 1
    assert create_calls[0]["workspace_id"] == WS
    assert create_calls[0]["email"] == "newhire@drinkx.tech"
    assert create_calls[0]["suggested_role"] == "manager"
    assert result is not None


# ===========================================================================
# 2. invite_user idempotent on existing invite
# ===========================================================================

@pytest.mark.asyncio
async def test_invite_user_idempotent_on_re_invite():
    """If an invite already exists for (workspace, email), invite_user
    should re-send the magic-link but NOT insert a duplicate row.
    Returns the existing row so the admin UI just refreshes the list."""
    db = AsyncMock()

    invite_calls: list[dict] = []
    create_calls: list[dict] = []

    existing = MagicMock()
    existing.id = uuid.uuid4()
    existing.email = "existing@drinkx.tech"

    async def fake_get_invite_by_email(_session, **kwargs):
        return existing

    async def fake_create_invite(_session, **kwargs):
        create_calls.append(kwargs)
        return MagicMock()

    async def fake_send(*, email):
        invite_calls.append({"email": email})

    with patch(
        "app.users.repositories.get_invite_by_email",
        new=fake_get_invite_by_email,
    ), patch(
        "app.users.repositories.create_invite",
        new=fake_create_invite,
    ), patch(
        "app.users.services.send_invite_email",
        new=fake_send,
    ):
        result = await svc.invite_user(
            db,
            workspace_id=WS,
            invited_by_user_id=ADMIN_ID,
            email="existing@drinkx.tech",
            role="manager",
        )

    # Magic-link re-sent, but no new row inserted.
    assert len(invite_calls) == 1
    assert len(create_calls) == 0
    assert result is existing


# ===========================================================================
# 3. invite_user fails on Supabase upstream error (no row created)
# ===========================================================================

@pytest.mark.asyncio
async def test_invite_user_aborts_on_supabase_error():
    """If Supabase fails to send the magic-link, we MUST NOT create
    the UserInvite row — otherwise the admin sees «invited» state for
    a user who never got an email."""
    from app.users.supabase_admin import SupabaseInviteError

    db = AsyncMock()
    create_calls: list[dict] = []

    async def fake_get_invite_by_email(_session, **kwargs):
        return None

    async def fake_create_invite(_session, **kwargs):
        create_calls.append(kwargs)
        return MagicMock()

    async def fake_send(*, email):
        raise SupabaseInviteError("Supabase 500: internal error")

    with patch(
        "app.users.repositories.get_invite_by_email",
        new=fake_get_invite_by_email,
    ), patch(
        "app.users.repositories.create_invite",
        new=fake_create_invite,
    ), patch(
        "app.users.services.send_invite_email",
        new=fake_send,
    ):
        with pytest.raises(svc.InviteSendFailed):
            await svc.invite_user(
                db,
                workspace_id=WS,
                invited_by_user_id=ADMIN_ID,
                email="upstream@drinkx.tech",
                role="manager",
            )

    assert len(create_calls) == 0


# ===========================================================================
# 4. change_role happy path
# ===========================================================================

@pytest.mark.asyncio
async def test_change_role_promotes_manager_to_admin():
    """Standard promotion: target manager → admin. The admin-count
    guard only fires on demotion, so a promotion goes straight
    through."""
    db = AsyncMock()
    target = _make_user(role="manager")
    update_calls: list[dict] = []

    async def fake_get_by_id(_session, **kwargs):
        return target

    async def fake_count_admins(_session, **kwargs):
        return 1  # would only matter on demote

    async def fake_update_role(_session, **kwargs):
        update_calls.append(kwargs)
        kwargs["user"].role = kwargs["role"]
        return kwargs["user"]

    with patch(
        "app.users.repositories.get_by_id", new=fake_get_by_id
    ), patch(
        "app.users.repositories.count_admins", new=fake_count_admins
    ), patch(
        "app.users.repositories.update_role", new=fake_update_role
    ):
        result = await svc.change_role(
            db,
            target_user_id=target.id,
            new_role="admin",
            workspace_id=WS,
        )

    assert result.role == "admin"
    assert len(update_calls) == 1


# ===========================================================================
# 5. change_role refuses to demote the LAST admin
# ===========================================================================

@pytest.mark.asyncio
async def test_change_role_refuses_demoting_last_admin():
    """The defensive guard MUST raise LastAdminRefusal (router → 409)
    when the target is currently admin AND would become non-admin AND
    they're the last admin in the workspace. Otherwise the workspace
    ends up with zero admins, leaving no one able to invite or
    promote."""
    db = AsyncMock()
    target = _make_user(role="admin")

    async def fake_get_by_id(_session, **kwargs):
        return target

    async def fake_count_admins(_session, **kwargs):
        return 1  # this user is the LAST admin

    with patch(
        "app.users.repositories.get_by_id", new=fake_get_by_id
    ), patch(
        "app.users.repositories.count_admins", new=fake_count_admins
    ):
        with pytest.raises(svc.LastAdminRefusal):
            await svc.change_role(
                db,
                target_user_id=target.id,
                new_role="manager",
                workspace_id=WS,
            )


# ===========================================================================
# 6. change_role allows demoting an admin when there are MORE admins
# ===========================================================================

@pytest.mark.asyncio
async def test_change_role_allows_demotion_when_other_admins_exist():
    """When workspace has ≥2 admins, demoting one of them is fine —
    the other admin keeps the workspace bootstrappable."""
    db = AsyncMock()
    target = _make_user(role="admin")
    update_calls: list[dict] = []

    async def fake_get_by_id(_session, **kwargs):
        return target

    async def fake_count_admins(_session, **kwargs):
        return 2  # plural

    async def fake_update_role(_session, **kwargs):
        update_calls.append(kwargs)
        kwargs["user"].role = kwargs["role"]
        return kwargs["user"]

    with patch(
        "app.users.repositories.get_by_id", new=fake_get_by_id
    ), patch(
        "app.users.repositories.count_admins", new=fake_count_admins
    ), patch(
        "app.users.repositories.update_role", new=fake_update_role
    ):
        result = await svc.change_role(
            db,
            target_user_id=target.id,
            new_role="manager",
            workspace_id=WS,
        )

    assert result.role == "manager"
    assert len(update_calls) == 1


# ===========================================================================
# 7. change_role validates the role string
# ===========================================================================

@pytest.mark.asyncio
async def test_change_role_rejects_invalid_role():
    """Invalid role strings raise InvalidRole (router → 400) instead
    of letting an arbitrary string land in the DB column."""
    db = AsyncMock()

    with pytest.raises(svc.InvalidRole):
        await svc.change_role(
            db,
            target_user_id=uuid.uuid4(),
            new_role="superadmin",
            workspace_id=WS,
        )


# ===========================================================================
# 8. invite_user validates the role string
# ===========================================================================

@pytest.mark.asyncio
async def test_invite_user_rejects_invalid_role():
    db = AsyncMock()

    with pytest.raises(svc.InvalidRole):
        await svc.invite_user(
            db,
            workspace_id=WS,
            invited_by_user_id=ADMIN_ID,
            email="x@y.io",
            role="god",
        )


# ===========================================================================
# 9. diff_engine carryover — no longer reads pipelines.is_default
# ===========================================================================

@pytest.mark.asyncio
async def test_diff_engine_resolves_default_via_workspace_fk():
    """Sprint 2.4 G1: diff_engine._resolve_stage_id used to query
    `Pipeline.is_default=true` directly. Migration 0017 drops that
    column. The new code path goes through
    `pipelines_repo.get_default_pipeline_id` which reads the
    canonical `workspaces.default_pipeline_id` FK.

    This test exercises the fall-through path: lead has no
    pipeline_id, the resolver should ASK the workspace for its
    default and then look up the stage by name in that pipeline."""
    from app.import_export import diff_engine as de_mod

    db = AsyncMock()
    workspace_id = uuid.uuid4()
    target_pipeline_id = uuid.uuid4()
    matched_stage_id = uuid.uuid4()

    lead = MagicMock()
    lead.workspace_id = workspace_id
    lead.pipeline_id = None  # forces the workspace-default lookup

    get_default_calls: list[dict] = []

    async def fake_get_default_pipeline_id(_session, **kwargs):
        get_default_calls.append(kwargs)
        return target_pipeline_id

    fake_stage_result = MagicMock()
    fake_stage_result.scalar_one_or_none = MagicMock(
        return_value=matched_stage_id
    )
    db.execute = AsyncMock(return_value=fake_stage_result)

    with patch(
        "app.pipelines.repositories.get_default_pipeline_id",
        new=fake_get_default_pipeline_id,
    ):
        result = await de_mod._resolve_stage_id(
            db, lead=lead, stage_name="Discovery"
        )

    assert result == matched_stage_id
    assert len(get_default_calls) == 1
    assert get_default_calls[0]["workspace_id"] == workspace_id
