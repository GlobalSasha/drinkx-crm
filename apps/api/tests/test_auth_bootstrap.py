"""Tests for app.auth.services.upsert_user_from_token.

Single-workspace model: first user creates the shared workspace +
bootstrap pipeline; every subsequent new user needs an invitation
to join it. Existing users continue to sign in normally.

Mock-only. Stubs sqlalchemy at import time so the ORM imports don't
drag the real declarative base in. Same pattern as
tests/test_pipelines_service.py + tests/test_webforms.py.
"""
from __future__ import annotations

import sys
import uuid
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# sqlalchemy stub (matches tests/test_pipelines_service.py)
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
        "Numeric", "DateTime", "Boolean", "Index", "select", "func",
        "desc", "false", "true", "UniqueConstraint", "text", "nullslast",
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


# ---------------------------------------------------------------------------
# SQLAlchemy filter-clause shims — class attrs the auth services read
# via `select(User).where(User.supabase_user_id == claims.sub)` etc.
# Under the stubbed sqlalchemy, the binary comparison short-circuits;
# we just need these attributes to exist on the spy classes so the
# attribute access itself doesn't AttributeError.
# ---------------------------------------------------------------------------

class _SAField:
    """Stub SQLAlchemy column descriptor — supports == / != for filter
    clauses. Returns a truthy MagicMock so the stubbed select/where
    treats it as a valid criterion."""
    def __eq__(self, other): return MagicMock()
    def __ne__(self, other): return MagicMock()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_claims(*, sub=None, email="user@drinkx.tech", name="Test User"):
    """Mock TokenClaims — only the fields upsert_user_from_token reads."""
    c = MagicMock()
    c.sub = sub or str(uuid.uuid4())
    c.email = email
    c.name = name
    return c


def _make_session_with_executes(execute_results):
    """Build an AsyncSession mock whose `.execute(...)` returns a sequence
    of MagicMock results in order. Each call's `.scalar_one_or_none()`
    or `.first()` returns the corresponding item from execute_results.

    `execute_results` items are either:
      - None: scalar_one_or_none returns None
      - (value,): scalar_one_or_none returns value
    """
    db = AsyncMock()
    db.flush = AsyncMock()

    call_index = {"i": 0}

    async def fake_execute(*_args, **_kwargs):
        i = call_index["i"]
        call_index["i"] += 1
        result = MagicMock()
        if i < len(execute_results):
            value = execute_results[i]
            result.scalar_one_or_none = MagicMock(return_value=value)
            result.first = MagicMock(return_value=value)
        else:
            result.scalar_one_or_none = MagicMock(return_value=None)
            result.first = MagicMock(return_value=None)
        return result

    db.execute = fake_execute
    db.add = MagicMock()
    return db


@pytest.fixture(autouse=True)
def _neutralize_select():
    """Patch the service's module-level `select` to a no-op.

    These tests pass spy classes (not mapped ORM models) into the service. In a
    full CI run real sqlalchemy is already imported (the module-level stub is
    skipped), so `select(_UserSpy)` would raise. The mocked session ignores the
    query object anyway, so a no-op select keeps the test independent of import
    order.
    """
    from app.auth import services as auth_svc

    with patch.object(auth_svc, "select", lambda *a, **k: MagicMock()):
        yield


# ---------------------------------------------------------------------------
# 1. First user creates the workspace
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_first_user_creates_workspace():
    """First-ever user signing in:
      - upsert finds no existing User (both lookups return None)
      - finds NO existing Workspace (the shared-workspace lookup
        returns None)
      - creates a Workspace named from settings.workspace_name
      - creates a Pipeline + 12 stages
      - sets workspaces.default_pipeline_id
      - creates the User as role='admin'
    """
    from app.auth import services as auth_svc

    workspaces_created: list = []
    pipelines_created: list = []
    stages_created: list = []
    users_created: list = []

    class _WorkspaceSpy:
        # SQLAlchemy filter-clause class attrs — accessed by
        # `select(Workspace).order_by(Workspace.created_at...)`. The
        # stubbed sqlalchemy ignores the actual values; these just
        # need to exist on the class.
        created_at = MagicMock()

        def __init__(self, **kw):
            workspaces_created.append(kw)
            for k, v in kw.items():
                setattr(self, k, v)
            self.id = uuid.uuid4()
            self.default_pipeline_id = None

    class _PipelineSpy:
        def __init__(self, **kw):
            pipelines_created.append(kw)
            for k, v in kw.items():
                setattr(self, k, v)
            self.id = uuid.uuid4()

    class _StageSpy:
        def __init__(self, **kw):
            stages_created.append(kw)

    class _UserSpy:
        supabase_user_id = _SAField()
        email = _SAField()
        workspace_id = _SAField()

        def __init__(self, **kw):
            users_created.append(kw)
            for k, v in kw.items():
                setattr(self, k, v)
            self.id = uuid.uuid4()

    fake_settings = MagicMock()
    fake_settings.workspace_name = "Acme Coffee Co"

    # Execute order in the new code:
    #   1. SELECT user by supabase_user_id  → None
    #   2. SELECT user by email             → None
    #   3. SELECT workspace ORDER BY created_at → None (no workspace yet)
    db = _make_session_with_executes([None, None, None])
    claims = _make_claims(email="founder@acme.co", name="Founder")

    with patch.object(auth_svc, "Workspace", _WorkspaceSpy), \
         patch.object(auth_svc, "Pipeline", _PipelineSpy), \
         patch.object(auth_svc, "Stage", _StageSpy), \
         patch.object(auth_svc, "User", _UserSpy), \
         patch.object(auth_svc, "get_settings", return_value=fake_settings), \
         patch(
             "app.lead_sources.repositories.seed_defaults",
             new=AsyncMock(return_value=5),
         ):
        user = await auth_svc.upsert_user_from_token(db, claims)

    assert user is not None
    assert len(workspaces_created) == 1
    assert workspaces_created[0]["name"] == "Acme Coffee Co"
    assert len(pipelines_created) == 1
    assert pipelines_created[0]["name"] == "Новые клиенты"
    # Sprint 2.4 G1: `is_default` column dropped (migration 0017).
    # The canonical default is set on the workspace via
    # `workspace.default_pipeline_id`, asserted below.
    assert "is_default" not in pipelines_created[0]
    assert len(stages_created) == 12  # full B2B template
    assert len(users_created) == 1
    assert users_created[0]["role"] == "admin"
    assert users_created[0]["email"] == "founder@acme.co"


# ---------------------------------------------------------------------------
# 2. Invited second user joins the existing workspace
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_invited_second_user_joins_existing_workspace():
    """Second user signing in:
      - upsert finds no existing User
      - DOES find an existing Workspace (the canonical shared one)
      - DOES NOT create a new Workspace, Pipeline, or Stages
      - finds a pending invitation for the same email
      - creates the User with the invited role against the existing
        workspace's id
    """
    from app.auth import services as auth_svc

    workspaces_created: list = []
    pipelines_created: list = []
    stages_created: list = []
    users_created: list = []

    class _WorkspaceSpy:
        created_at = MagicMock()
        def __init__(self, **kw):
            workspaces_created.append(kw)

    class _PipelineSpy:
        def __init__(self, **kw):
            pipelines_created.append(kw)

    class _StageSpy:
        def __init__(self, **kw):
            stages_created.append(kw)

    class _UserSpy:
        supabase_user_id = _SAField()
        email = _SAField()
        workspace_id = _SAField()

        def __init__(self, **kw):
            users_created.append(kw)
            for k, v in kw.items():
                setattr(self, k, v)
            self.id = uuid.uuid4()

    fake_settings = MagicMock()
    fake_settings.workspace_name = "DrinkX"

    # Pre-existing workspace returned by the third execute call.
    existing_workspace_id = uuid.uuid4()
    existing_workspace = MagicMock()
    existing_workspace.id = existing_workspace_id
    pending_invite = MagicMock()
    pending_invite.suggested_role = "head"
    pending_invite.accepted_at = None
    pending_invite.invited_by_user_id = uuid.uuid4()
    pending_invite.workspace_id = existing_workspace_id
    pending_invite.email = "newhire@drinkx.tech"

    # Execute order:
    #   1. SELECT user by supabase_user_id  → None
    #   2. SELECT user by email             → None
    #   3. SELECT workspace ORDER BY created_at → existing_workspace
    #   4. SELECT pending invite             → pending_invite
    #   5. accept-flow invite lookup         → pending_invite
    db = _make_session_with_executes(
        [None, None, existing_workspace, pending_invite, pending_invite]
    )
    claims = _make_claims(email="newhire@drinkx.tech", name="New Hire")

    with patch.object(auth_svc, "Workspace", _WorkspaceSpy), \
         patch.object(auth_svc, "Pipeline", _PipelineSpy), \
         patch.object(auth_svc, "Stage", _StageSpy), \
         patch.object(auth_svc, "User", _UserSpy), \
         patch.object(auth_svc, "get_settings", return_value=fake_settings):
        user = await auth_svc.upsert_user_from_token(db, claims)

    assert user is not None
    assert len(workspaces_created) == 0, (
        "second user must not create a new workspace"
    )
    assert len(pipelines_created) == 0, (
        "second user must not bootstrap a pipeline — that's the existing workspace's"
    )
    assert len(stages_created) == 0
    assert len(users_created) == 1
    assert users_created[0]["role"] == "head", (
        "new users receive the role selected in their invitation"
    )
    assert users_created[0]["email"] == "newhire@drinkx.tech"
    assert users_created[0]["workspace_id"] == existing_workspace_id, (
        "second user must be attached to the existing workspace, not a new one"
    )
    assert pending_invite.accepted_at is not None


@pytest.mark.asyncio
async def test_uninvited_new_user_is_rejected():
    """A valid Supabase/Google identity is not enough to join CRM."""
    from app.auth import services as auth_svc

    class _UserSpy:
        supabase_user_id = _SAField()
        email = _SAField()

    existing_workspace = MagicMock()
    existing_workspace.id = uuid.uuid4()
    db = _make_session_with_executes([None, None, existing_workspace, None])

    with patch.object(auth_svc, "User", _UserSpy):
        with pytest.raises(auth_svc.InviteRequired):
            await auth_svc.upsert_user_from_token(
                db,
                _make_claims(email="stranger@example.com"),
            )

    assert db.add.call_count == 0


# ---------------------------------------------------------------------------
# 3. Existing user — no workspace creation, just last_login update
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_existing_user_just_updates_last_login():
    """User who has signed in before: upsert finds them by
    supabase_user_id (or email fallback), updates last_login_at,
    and returns. Never creates a workspace."""
    from app.auth import services as auth_svc

    workspaces_created: list = []
    users_created: list = []

    class _WorkspaceSpy:
        created_at = MagicMock()
        def __init__(self, **kw):
            workspaces_created.append(kw)

    class _UserSpy:
        supabase_user_id = _SAField()
        email = _SAField()
        workspace_id = _SAField()

        def __init__(self, **kw):
            users_created.append(kw)

    existing_user = MagicMock()
    existing_user.supabase_user_id = "sub-abc"
    existing_user.name = "Existing"
    existing_user.last_login_at = None

    db = _make_session_with_executes([existing_user])
    claims = _make_claims(sub="sub-abc", email="existing@drinkx.tech")

    with patch.object(auth_svc, "Workspace", _WorkspaceSpy), \
         patch.object(auth_svc, "User", _UserSpy):
        user = await auth_svc.upsert_user_from_token(db, claims)

    assert user is existing_user
    assert len(workspaces_created) == 0
    assert len(users_created) == 0
    assert existing_user.last_login_at is not None
