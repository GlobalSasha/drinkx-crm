"""Tests for app.audit — Sprint 1.5 group 3.

SQLAlchemy stubbed at import time (same pattern as test_notifications.py).
Service functions tested with AsyncMock DB sessions — no Postgres needed.
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

    def _noop(*a, **kw):
        return None

    class _Callable:
        def __init__(self, *a, **kw): pass
        def __call__(self, *a, **kw): return _Callable()
        def __class_getitem__(cls, item): return cls
        def __getattr__(self, name): return _Callable()
        def __eq__(self, other): return True
        def __ne__(self, other): return True

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

import app.audit.audit as audit_mod  # noqa: E402
import app.audit.repositories as repo_mod  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock()
    return db


def _make_user(role: str = "admin"):
    user = MagicMock()
    user.id = uuid.uuid4()
    user.workspace_id = uuid.uuid4()
    user.role = role
    return user


# ---------------------------------------------------------------------------
# 1. log() stages a row with correct fields
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_audit_log_creates_row():
    """log() builds an AuditLog with supplied kwargs and calls session.add()."""
    db = _make_db()
    workspace_id = uuid.uuid4()
    user_id = uuid.uuid4()
    entity_id = uuid.uuid4()

    fake_row = MagicMock()
    with patch.object(audit_mod, "AuditLog", return_value=fake_row) as MockAuditLog:
        await audit_mod.log(
            db,
            action="lead.transfer",
            workspace_id=workspace_id,
            user_id=user_id,
            entity_type="lead",
            entity_id=entity_id,
            delta={"from": "x", "to": "y"},
        )

    assert MockAuditLog.call_args is not None
    kwargs = dict(MockAuditLog.call_args.kwargs)
    assert kwargs["workspace_id"] == workspace_id
    assert kwargs["user_id"] == user_id
    assert kwargs["action"] == "lead.transfer"
    assert kwargs["entity_type"] == "lead"
    assert kwargs["entity_id"] == entity_id
    assert kwargs["delta_json"] == {"from": "x", "to": "y"}
    db.add.assert_called_once_with(fake_row)


@pytest.mark.asyncio
async def test_audit_log_accepts_null_user_for_system_events():
    """user_id=None is valid (system-triggered actions, no human actor)."""
    db = _make_db()
    fake_row = MagicMock()

    with patch.object(audit_mod, "AuditLog", return_value=fake_row) as MockAuditLog:
        await audit_mod.log(
            db,
            action="enrichment.trigger",
            workspace_id=uuid.uuid4(),
            user_id=None,
            entity_type="lead",
            entity_id=uuid.uuid4(),
            delta=None,
        )

    kwargs = dict(MockAuditLog.call_args.kwargs)
    assert kwargs["user_id"] is None
    assert kwargs["delta_json"] is None


# ---------------------------------------------------------------------------
# 2. log() swallows exceptions — never raises
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_audit_log_swallows_exception():
    """If session.add() raises, log() must NOT propagate the exception."""
    db = _make_db()
    db.add = MagicMock(side_effect=RuntimeError("session detached"))

    # Must not raise
    result = await audit_mod.log(
        db,
        action="lead.create",
        workspace_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        entity_type="lead",
        entity_id=uuid.uuid4(),
        delta={"company_name": "Acme"},
    )
    assert result is None  # log() returns None implicitly


# ---------------------------------------------------------------------------
# 3. /api/audit requires admin role
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_audit_endpoint_requires_admin():
    """The require_admin dependency must reject non-admin users with HTTP 403.
    /api/audit uses this dependency, so any non-admin → 403 before DB query."""
    from fastapi import HTTPException

    from app.auth.dependencies import require_admin

    manager = _make_user(role="manager")
    with pytest.raises(HTTPException) as exc_info:
        await require_admin(user=manager)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_audit_endpoint_admin_passes_through():
    """Admin users go through the gate untouched."""
    from app.auth.dependencies import require_admin

    admin = _make_user(role="admin")
    result = await require_admin(user=admin)
    assert result is admin


# ---------------------------------------------------------------------------
# 4. Endpoint scopes to caller's workspace_id (not arbitrary)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_audit_endpoint_filters_by_callers_workspace():
    """list_audit() passes user.workspace_id straight into the repo, never an
    arbitrary value — workspace isolation is non-negotiable."""
    from app.audit.routers import list_audit

    db = _make_db()
    admin = _make_user(role="admin")
    callers_ws = admin.workspace_id

    with patch.object(repo_mod, "list_for_workspace", new=AsyncMock(return_value=([], 0))) as mock_repo:
        result = await list_audit(
            entity_type=None,
            entity_id=None,
            page=1,
            page_size=50,
            db=db,
            user=admin,
        )

    # Repo called with the admin's workspace_id, not anything else
    assert mock_repo.await_count == 1
    repo_kwargs = mock_repo.await_args.kwargs
    assert repo_kwargs["workspace_id"] == callers_ws
    assert repo_kwargs["entity_type"] is None
    assert repo_kwargs["entity_id"] is None
    assert repo_kwargs["page"] == 1
    assert repo_kwargs["page_size"] == 50
    assert result.items == []
    assert result.total == 0


# ---------------------------------------------------------------------------
# 5. transfer_lead() emits audit.log with action="lead.transfer"
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_transfer_lead_writes_audit():
    """After transfer_lead succeeds, audit.log is called with action='lead.transfer'
    and the from/to assignee in delta."""
    import app.leads.services as leads_svc

    db = _make_db()
    workspace_id = uuid.uuid4()
    current_user_id = uuid.uuid4()
    lead_id = uuid.uuid4()
    old_owner = uuid.uuid4()
    new_owner = uuid.uuid4()

    # Mock the Lead row returned by repo.get_by_id
    mock_lead = MagicMock()
    mock_lead.id = lead_id
    mock_lead.assigned_to = old_owner
    mock_lead.company_name = "Acme"

    # Mock the transferred row
    mock_transferred = MagicMock()
    mock_transferred.id = lead_id
    mock_transferred.company_name = "Acme"

    # Mock the target user lookup — returns a non-None MagicMock so the
    # transfer-target validation passes
    target_user_result = MagicMock()
    target_user_result.scalar_one_or_none.return_value = MagicMock()
    db.execute = AsyncMock(return_value=target_user_result)

    with (
        patch("app.leads.repositories.get_by_id", new=AsyncMock(return_value=mock_lead)),
        patch("app.leads.repositories.transfer_lead", new=AsyncMock(return_value=mock_transferred)),
        patch("app.notifications.services.safe_notify", new=AsyncMock(return_value=None)),
        patch("app.audit.audit.log", new=AsyncMock(return_value=None)) as mock_audit,
    ):
        await leads_svc.transfer_lead(
            db,
            workspace_id=workspace_id,
            current_user_id=current_user_id,
            current_user_role="admin",  # bypasses ownership check
            lead_id=lead_id,
            to_user_id=new_owner,
            comment="handing over",
        )

    assert mock_audit.await_count == 1
    audit_kwargs = mock_audit.await_args.kwargs
    assert audit_kwargs["action"] == "lead.transfer"
    assert audit_kwargs["workspace_id"] == workspace_id
    assert audit_kwargs["user_id"] == current_user_id
    assert audit_kwargs["entity_type"] == "lead"
    assert audit_kwargs["entity_id"] == lead_id
    assert audit_kwargs["delta"] == {
        "from": str(old_owner),
        "to": str(new_owner),
    }
