"""Tests for app.template.services — Sprint 2.4 G4.

Mock-only — same sqlalchemy stub pattern as test_users_service.py.
Six scenarios spec'd for G4 covered at the service layer (codebase's
mock-baseline pattern). Role gating is a router-level concern
(`require_admin` dependency); the service itself is role-agnostic so
managers reading the list goes through the same code path as admin
mutating it — exercised by test_list_templates_scoped_to_workspace.
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
        # Sprint 2.6 stability fix: TemplateInUse query uses
        # `Automation.action_config_json["template_id"]` (JSON-key
        # access). The stub's columns are `_Callable` instances; need
        # `__getitem__` to keep the SELECT-builder compiling under the
        # mock-only test path.
        def __getitem__(self, key): return _Callable()
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

from app.template import services as svc  # noqa: E402

WS = uuid.uuid4()
ADMIN_ID = uuid.uuid4()


def _make_template(*, id_=None, name="Welcome", channel="email", category=None):
    t = MagicMock()
    t.id = id_ or uuid.uuid4()
    t.workspace_id = WS
    t.name = name
    t.channel = channel
    t.category = category
    t.text = "Hello {{lead.name}}"
    return t


# ===========================================================================
# 1. GET → list scoped to workspace, passes channel filter through
# ===========================================================================

@pytest.mark.asyncio
async def test_list_templates_scoped_to_workspace():
    """The service simply forwards `workspace_id` and the optional
    `channel` filter to the repo. Role-agnostic — readable by every
    role, the router decides who can call it."""
    db = AsyncMock()
    repo_calls: list[dict] = []

    async def fake_list_for_workspace(_db, **kw):
        repo_calls.append(kw)
        return [_make_template(name="A"), _make_template(name="B")]

    with patch(
        "app.template.repositories.list_for_workspace",
        new=fake_list_for_workspace,
    ):
        rows = await svc.list_templates(
            db, workspace_id=WS, channel="email"
        )

    assert len(rows) == 2
    assert len(repo_calls) == 1
    assert repo_calls[0]["workspace_id"] == WS
    assert repo_calls[0]["channel"] == "email"


# ===========================================================================
# 2. POST → 201 happy path: trims name + persists
# ===========================================================================

@pytest.mark.asyncio
async def test_create_template_happy_path():
    """Standard create: trims name + delegates to repo. created_by
    flows through so the audit trail can later attribute who made it."""
    db = AsyncMock()
    create_calls: list[dict] = []

    async def fake_get_by_name_and_channel(_db, **kw):
        return None

    async def fake_create(_db, **kw):
        create_calls.append(kw)
        out = _make_template(name=kw["name"], channel=kw["channel"])
        return out

    with patch(
        "app.template.repositories.get_by_name_and_channel",
        new=fake_get_by_name_and_channel,
    ), patch(
        "app.template.repositories.create", new=fake_create
    ):
        result = await svc.create_template(
            db,
            workspace_id=WS,
            created_by=ADMIN_ID,
            name="  Welcome  ",  # whitespace trims
            channel="email",
            category="onboarding",
            text="Hello",
        )

    assert len(create_calls) == 1
    args = create_calls[0]
    assert args["name"] == "Welcome"
    assert args["channel"] == "email"
    assert args["created_by"] == ADMIN_ID
    assert result.name == "Welcome"


# ===========================================================================
# 3. POST duplicate name+channel → DuplicateTemplate (router → 409)
# ===========================================================================

@pytest.mark.asyncio
async def test_create_template_rejects_duplicate_name_channel():
    """Workspace already has a template with this (name, channel)
    pair → raise DuplicateTemplate carrying both. The router maps to
    a structured 409 detail (`code: duplicate_template`) the UI uses
    to render an inline collision message."""
    db = AsyncMock()
    existing = _make_template(name="Welcome", channel="email")

    async def fake_get_by_name_and_channel(_db, **kw):
        return existing

    with patch(
        "app.template.repositories.get_by_name_and_channel",
        new=fake_get_by_name_and_channel,
    ):
        with pytest.raises(svc.DuplicateTemplate) as exc_info:
            await svc.create_template(
                db,
                workspace_id=WS,
                created_by=ADMIN_ID,
                name="Welcome",
                channel="email",
                category=None,
                text="Hi",
            )

    # Exception carries the offending pair so the router can echo it
    # in the 409 detail.
    assert exc_info.value.name == "Welcome"
    assert exc_info.value.channel == "email"


# ===========================================================================
# 4. PATCH → updates the row in place
# ===========================================================================

@pytest.mark.asyncio
async def test_update_template_happy_path():
    """Patch passes through to repo.update with the trimmed name,
    leaving unspecified fields untouched (None = no-op for non-
    nullable fields, category_set defaults to False so category
    isn't accidentally cleared)."""
    db = AsyncMock()
    target = _make_template(name="Old", channel="email")
    update_calls: list[dict] = []

    async def fake_get_by_id(_db, **kw):
        return target

    # No (name, channel) clash — `update_template` only checks when
    # name OR channel actually changes; here only name changes.
    async def fake_get_by_name_and_channel(_db, **kw):
        return None

    async def fake_update(_db, **kw):
        update_calls.append(kw)
        kw["template"].name = kw["name"] or kw["template"].name
        return kw["template"]

    with patch(
        "app.template.repositories.get_by_id", new=fake_get_by_id
    ), patch(
        "app.template.repositories.get_by_name_and_channel",
        new=fake_get_by_name_and_channel,
    ), patch(
        "app.template.repositories.update", new=fake_update
    ):
        result = await svc.update_template(
            db,
            template_id=target.id,
            workspace_id=WS,
            name="  New  ",  # trims
        )

    assert result.name == "New"
    assert len(update_calls) == 1
    # Channel + text not touched — repo gets None for them.
    assert update_calls[0]["channel"] is None
    assert update_calls[0]["text"] is None


# ===========================================================================
# 5. DELETE → calls repo.delete on the matched row
# ===========================================================================

def _patch_in_use_returns(automation_id):
    """Helper for the Sprint 2.6 stability TemplateInUse guard. The
    `delete_template` service runs an `Automation` SELECT joined on
    `action_config_json["template_id"]` before calling repo.delete.
    Tests stub `db.execute` so the SELECT returns either an offending
    automation id (→ TemplateInUse) or None (→ proceeds to delete)."""
    res = MagicMock()
    res.scalar_one_or_none = MagicMock(return_value=automation_id)
    return AsyncMock(return_value=res)


@pytest.mark.asyncio
async def test_delete_template_happy_path():
    """Service fetches by id (workspace-scoped) → checks no active
    automation references it → forwards to repo.delete. Cross-
    workspace id raises TemplateNotFound — covered by the not-found
    test below."""
    db = AsyncMock()
    db.execute = _patch_in_use_returns(None)  # no active automation references
    target = _make_template()
    delete_calls: list[dict] = []

    async def fake_get_by_id(_db, **kw):
        return target

    async def fake_delete(_db, **kw):
        delete_calls.append(kw)

    with patch(
        "app.template.repositories.get_by_id", new=fake_get_by_id
    ), patch(
        "app.template.repositories.delete", new=fake_delete
    ):
        await svc.delete_template(
            db, template_id=target.id, workspace_id=WS
        )

    assert len(delete_calls) == 1
    assert delete_calls[0]["template"] is target


@pytest.mark.asyncio
async def test_delete_template_refuses_when_referenced_by_active_automation():
    """Sprint 2.6 stability fix: deleting a template that an active
    automation references via `action_config_json["template_id"]`
    must raise `TemplateInUse` carrying the offending automation id.
    Mirrors the Sprint 2.3 PipelineHasLeads pattern — router maps to
    a structured 409 with the automation_id in the body. Without
    this guard, the next fan-out fire would log
    `automation_runs.status='failed'` with «template not found» and
    the admin would have no idea why."""
    db = AsyncMock()
    referencing_automation_id = uuid.uuid4()
    db.execute = _patch_in_use_returns(referencing_automation_id)
    target = _make_template()

    delete_calls: list[dict] = []

    async def fake_get_by_id(_db, **kw):
        return target

    async def fake_delete(_db, **kw):
        delete_calls.append(kw)  # must NOT be reached

    with patch(
        "app.template.repositories.get_by_id", new=fake_get_by_id
    ), patch(
        "app.template.repositories.delete", new=fake_delete
    ):
        with pytest.raises(svc.TemplateInUse) as exc_info:
            await svc.delete_template(
                db, template_id=target.id, workspace_id=WS
            )

    # Guard fired before the repo.delete call — template stays in DB.
    assert len(delete_calls) == 0
    # Exception carries the offending id for the structured 409.
    assert exc_info.value.automation_id == referencing_automation_id


# ===========================================================================
# 6. PATCH rename collision with a DIFFERENT existing row → 409
# ===========================================================================

@pytest.mark.asyncio
async def test_update_template_rejects_rename_into_existing_pair():
    """Renaming template A to a (name, channel) pair already taken by
    template B raises DuplicateTemplate — same shape as the create
    path. Without this guard a rename would silently fail at the DB
    integrity layer mid-transaction."""
    db = AsyncMock()
    target = _make_template(id_=uuid.uuid4(), name="A", channel="email")
    clash = _make_template(id_=uuid.uuid4(), name="B", channel="email")

    async def fake_get_by_id(_db, **kw):
        return target

    async def fake_get_by_name_and_channel(_db, **kw):
        # Asked about ("B", "email") — that's `clash`, a DIFFERENT row.
        return clash

    with patch(
        "app.template.repositories.get_by_id", new=fake_get_by_id
    ), patch(
        "app.template.repositories.get_by_name_and_channel",
        new=fake_get_by_name_and_channel,
    ):
        with pytest.raises(svc.DuplicateTemplate):
            await svc.update_template(
                db,
                template_id=target.id,
                workspace_id=WS,
                name="B",  # collides with clash
            )
