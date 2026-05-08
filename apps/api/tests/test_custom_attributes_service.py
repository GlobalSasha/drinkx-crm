"""Tests for app.custom_attributes.services — Sprint 2.4 G3.

Mock-only — same sqlalchemy stub pattern as test_users_service.py.
Covers definition CRUD validation + value upsert dispatch by kind.
"""
from __future__ import annotations

import datetime as _dt
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

from app.custom_attributes import services as svc  # noqa: E402

WS = uuid.uuid4()
LEAD = uuid.uuid4()


def _make_definition(*, kind="text", key="region", options=None):
    d = MagicMock()
    d.id = uuid.uuid4()
    d.workspace_id = WS
    d.key = key
    d.label = key.title()
    d.kind = kind
    d.options_json = options
    d.is_required = False
    d.position = 0
    return d


# ===========================================================================
# 1. create — happy path
# ===========================================================================

@pytest.mark.asyncio
async def test_create_definition_happy_path():
    """Standard create with kind=text. The service auto-assigns
    `position` via repo.next_position so the caller doesn't have to
    track ordering."""
    db = AsyncMock()
    create_calls: list[dict] = []

    async def fake_get_by_key(_db, **kw):
        return None

    async def fake_next_position(_db, **kw):
        return 3

    async def fake_create(_db, **kw):
        create_calls.append(kw)
        out = MagicMock()
        for k, v in kw.items():
            setattr(out, k, v)
        out.id = uuid.uuid4()
        return out

    with patch(
        "app.custom_attributes.repositories.get_by_key", new=fake_get_by_key
    ), patch(
        "app.custom_attributes.repositories.next_position",
        new=fake_next_position,
    ), patch(
        "app.custom_attributes.repositories.create_definition",
        new=fake_create,
    ):
        result = await svc.create_definition(
            db,
            workspace_id=WS,
            key="Region",  # mixed case input — service lowercases
            label="  Регион  ",  # trims
            kind="text",
            options_json=None,
            is_required=False,
        )

    assert len(create_calls) == 1
    args = create_calls[0]
    assert args["key"] == "region"
    assert args["label"] == "Регион"
    assert args["position"] == 3
    assert result.kind == "text"


# ===========================================================================
# 2. create — invalid key shape rejected
# ===========================================================================

@pytest.mark.asyncio
async def test_create_definition_rejects_bad_key_shape():
    """Keys must be lowercase ASCII identifiers. Anything weirder
    (e.g. dots, dashes, leading digits) gets a clear 400 instead of
    landing in the URL."""
    db = AsyncMock()
    with pytest.raises(svc.InvalidKey):
        await svc.create_definition(
            db,
            workspace_id=WS,
            key="1bad-key.with stuff",
            label="oops",
            kind="text",
            options_json=None,
            is_required=False,
        )


# ===========================================================================
# 3. create — duplicate key rejected
# ===========================================================================

@pytest.mark.asyncio
async def test_create_definition_rejects_duplicate_key():
    """Workspace already has a definition with this key → 409, not a
    DB-level unique-violation crash mid-transaction."""
    db = AsyncMock()
    existing = _make_definition(key="region")

    async def fake_get_by_key(_db, **kw):
        return existing

    with patch(
        "app.custom_attributes.repositories.get_by_key", new=fake_get_by_key
    ):
        with pytest.raises(svc.DuplicateKey):
            await svc.create_definition(
                db,
                workspace_id=WS,
                key="region",
                label="Region",
                kind="text",
                options_json=None,
                is_required=False,
            )


# ===========================================================================
# 4. create — kind=select demands options
# ===========================================================================

@pytest.mark.asyncio
async def test_create_definition_select_requires_options():
    """A select with no options is meaningless — surface as 400 before
    the row hits the DB. Otherwise the UI would render a dropdown
    with zero entries forever."""
    db = AsyncMock()

    async def fake_get_by_key(_db, **kw):
        return None

    with patch(
        "app.custom_attributes.repositories.get_by_key", new=fake_get_by_key
    ):
        with pytest.raises(svc.MissingOptions):
            await svc.create_definition(
                db,
                workspace_id=WS,
                key="region",
                label="Region",
                kind="select",
                options_json=None,
                is_required=False,
            )


# ===========================================================================
# 5. delete — not found → 404
# ===========================================================================

@pytest.mark.asyncio
async def test_delete_definition_not_found():
    """Cross-workspace lookup returns None from the repo; the service
    raises DefinitionNotFound which the router maps to 404."""
    db = AsyncMock()

    async def fake_get_definition(_db, **kw):
        return None

    with patch(
        "app.custom_attributes.repositories.get_definition",
        new=fake_get_definition,
    ):
        with pytest.raises(svc.DefinitionNotFound):
            await svc.delete_definition(
                db, definition_id=uuid.uuid4(), workspace_id=WS
            )


# ===========================================================================
# 6. upsert_value — dispatches text vs number per kind
# ===========================================================================

@pytest.mark.asyncio
async def test_upsert_value_dispatches_by_kind():
    """For kind='number', service writes value_number (not value_text)
    even if the caller passes both. The polymorphic columns stay
    consistent with the definition's kind."""
    db = AsyncMock()
    definition = _make_definition(kind="number")
    upsert_calls: list[dict] = []

    async def fake_get_definition(_db, **kw):
        return definition

    async def fake_upsert(_db, **kw):
        upsert_calls.append(kw)
        return MagicMock()

    with patch(
        "app.custom_attributes.repositories.get_definition",
        new=fake_get_definition,
    ), patch(
        "app.custom_attributes.repositories.upsert_value", new=fake_upsert
    ):
        await svc.upsert_value(
            db,
            workspace_id=WS,
            lead_id=LEAD,
            definition_id=definition.id,
            value_number=42.0,
        )

    assert len(upsert_calls) == 1
    assert upsert_calls[0]["value_number"] == 42.0
    # Other typed columns explicitly set to None — keeps the row clean
    # of stray writes.
    assert upsert_calls[0]["value_text"] is None
    assert upsert_calls[0]["value_date"] is None


# ===========================================================================
# 7. upsert_value — rejects mismatched value type
# ===========================================================================

@pytest.mark.asyncio
async def test_upsert_value_rejects_wrong_typed_value_for_kind():
    """Service refuses to silently coerce — passing value_number for
    kind='text' is a 400, not a write to the wrong column."""
    db = AsyncMock()
    definition = _make_definition(kind="text")

    async def fake_get_definition(_db, **kw):
        return definition

    with patch(
        "app.custom_attributes.repositories.get_definition",
        new=fake_get_definition,
    ):
        with pytest.raises(svc.InvalidValueForKind):
            await svc.upsert_value(
                db,
                workspace_id=WS,
                lead_id=LEAD,
                definition_id=definition.id,
                value_number=99.0,  # wrong shape
            )


# ===========================================================================
# 8. upsert_value — select requires the value be in options
# ===========================================================================

@pytest.mark.asyncio
async def test_upsert_value_select_validates_against_options():
    """For kind='select', the submitted value_text must be one of the
    options. Anything else is 400 — protects against stale UI bundles
    that send removed options."""
    db = AsyncMock()
    definition = _make_definition(
        kind="select",
        options=[{"value": "emea", "label": "EMEA"}, {"value": "apac", "label": "APAC"}],
    )

    async def fake_get_definition(_db, **kw):
        return definition

    with patch(
        "app.custom_attributes.repositories.get_definition",
        new=fake_get_definition,
    ):
        with pytest.raises(svc.InvalidValueForKind):
            await svc.upsert_value(
                db,
                workspace_id=WS,
                lead_id=LEAD,
                definition_id=definition.id,
                value_text="latam",  # not in options
            )


# ===========================================================================
# 9. upsert_value — date dispatch happy path
# ===========================================================================

@pytest.mark.asyncio
async def test_upsert_value_date_dispatch():
    """For kind='date', value_date is written and the other columns
    are nulled — exercises the third branch of the dispatch."""
    db = AsyncMock()
    definition = _make_definition(kind="date", key="signed_at")
    upsert_calls: list[dict] = []

    async def fake_get_definition(_db, **kw):
        return definition

    async def fake_upsert(_db, **kw):
        upsert_calls.append(kw)
        return MagicMock()

    target = _dt.date(2026, 5, 8)
    with patch(
        "app.custom_attributes.repositories.get_definition",
        new=fake_get_definition,
    ), patch(
        "app.custom_attributes.repositories.upsert_value", new=fake_upsert
    ):
        await svc.upsert_value(
            db,
            workspace_id=WS,
            lead_id=LEAD,
            definition_id=definition.id,
            value_date=target,
        )

    assert len(upsert_calls) == 1
    assert upsert_calls[0]["value_date"] == target
    assert upsert_calls[0]["value_text"] is None
    assert upsert_calls[0]["value_number"] is None
