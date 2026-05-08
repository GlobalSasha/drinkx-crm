"""Tests for app.settings.services AI section — Sprint 2.4 G3.

Mock-only — same sqlalchemy stub pattern as test_users_service.py.
Covers the get / update flow + validation guards.
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

from app.settings import services as svc  # noqa: E402

WS = uuid.uuid4()


def _make_workspace(*, settings_json=None):
    """ORM-like stand-in. Matches the shape services.update_ai_settings
    expects (a `settings_json` dict it can replace)."""
    w = MagicMock()
    w.id = WS
    w.settings_json = settings_json or {}
    return w


def _patch_workspace_load(workspace, db):
    """Make `db.execute(...).scalar_one_or_none()` return `workspace`."""
    res = MagicMock()
    res.scalar_one_or_none = MagicMock(return_value=workspace)
    db.execute = AsyncMock(return_value=res)


# ===========================================================================
# 1. get returns env defaults when settings_json["ai"] is empty
# ===========================================================================

@pytest.mark.asyncio
async def test_get_ai_settings_returns_env_defaults_when_unset():
    """Workspace hasn't picked overrides yet → response uses the env's
    monthly budget / 30 + the first item of llm_fallback_chain."""
    db = AsyncMock()
    workspace = _make_workspace(settings_json={})
    _patch_workspace_load(workspace, db)

    async def fake_spend(_ws_id):
        return 0.0

    with patch(
        "app.settings.services.get_daily_spend_usd", new=fake_spend
    ):
        result = await svc.get_ai_settings(db, workspace_id=WS)

    # Defaults derive from app.config.Settings — assert the SHAPE
    # rather than exact values so the test doesn't break when the env
    # default shifts.
    assert "daily_budget_usd" in result
    assert isinstance(result["daily_budget_usd"], float)
    assert result["primary_model"] in result["available_models"]
    assert result["current_spend_usd_today"] == 0.0


# ===========================================================================
# 2. get returns workspace overrides when present
# ===========================================================================

@pytest.mark.asyncio
async def test_get_ai_settings_uses_workspace_overrides():
    """When settings_json["ai"] has values, they win over env defaults.
    Spend is read from Redis (mocked) and surfaced verbatim."""
    db = AsyncMock()
    workspace = _make_workspace(
        settings_json={
            "ai": {"daily_budget_usd": 12.5, "primary_model": "anthropic"}
        }
    )
    _patch_workspace_load(workspace, db)

    async def fake_spend(_ws_id):
        return 3.21

    with patch(
        "app.settings.services.get_daily_spend_usd", new=fake_spend
    ):
        result = await svc.get_ai_settings(db, workspace_id=WS)

    assert result["daily_budget_usd"] == 12.5
    assert result["primary_model"] == "anthropic"
    assert result["current_spend_usd_today"] == 3.21


# ===========================================================================
# 3. update writes overrides into workspace.settings_json["ai"]
# ===========================================================================

@pytest.mark.asyncio
async def test_update_ai_settings_persists_overrides():
    """PATCH stores the new values on `settings_json["ai"]`. Both
    fields are written when both are passed."""
    db = AsyncMock()
    workspace = _make_workspace(settings_json={"other": "untouched"})
    _patch_workspace_load(workspace, db)

    async def fake_spend(_ws_id):
        return 0.0

    with patch(
        "app.settings.services.get_daily_spend_usd", new=fake_spend
    ):
        result = await svc.update_ai_settings(
            db,
            workspace_id=WS,
            daily_budget_usd=5.0,
            primary_model="gemini",
        )

    # Workspace.settings_json was reassigned (not mutated in place) —
    # SQLAlchemy needs the replacement to track the change on JSON
    # columns reliably.
    assert workspace.settings_json["ai"] == {
        "daily_budget_usd": 5.0,
        "primary_model": "gemini",
    }
    # Other top-level keys are preserved.
    assert workspace.settings_json["other"] == "untouched"
    assert result["primary_model"] == "gemini"
    assert result["daily_budget_usd"] == 5.0


# ===========================================================================
# 4. update rejects negative budget
# ===========================================================================

@pytest.mark.asyncio
async def test_update_ai_settings_rejects_negative_budget():
    """A negative cap would silently disable budget enforcement —
    surface as InvalidBudget so the router maps to 400."""
    db = AsyncMock()
    with pytest.raises(svc.InvalidBudget):
        await svc.update_ai_settings(
            db, workspace_id=WS, daily_budget_usd=-1.0
        )


# ===========================================================================
# 5. update rejects unknown model
# ===========================================================================

@pytest.mark.asyncio
async def test_update_ai_settings_rejects_unknown_model():
    """Anything not in AI_MODEL_CHOICES raises InvalidAIModel — keeps
    the workspace.settings_json string aligned with the enrichment
    factory registry."""
    db = AsyncMock()
    with pytest.raises(svc.InvalidAIModel):
        await svc.update_ai_settings(
            db, workspace_id=WS, primary_model="gpt-9000"
        )
