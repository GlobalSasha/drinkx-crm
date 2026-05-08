"""Tests for app.import_export.services — Sprint 2.1 G1 skeleton.

Mock-only: SQLAlchemy stubbed at import time, sessions are AsyncMock,
no Postgres / no network. Group 2 will add the upload/parse/preview tests.
"""
from __future__ import annotations

import sys
import uuid
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

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
        "desc", "false", "UniqueConstraint", "text", "nullslast",
        "asc", "or_", "and_", "update", "delete", "cast", "literal",
        "Date",
    ):
        setattr(sa, name, _Callable)

    class _Func:
        def __getattr__(self, name):
            return _Callable
    sa.func = _Func()

    sa_async = ModuleType("sqlalchemy.ext.asyncio")
    sa_pg = ModuleType("sqlalchemy.dialects.postgresql")
    sa_orm = ModuleType("sqlalchemy.orm")
    sa_ext = ModuleType("sqlalchemy.ext")
    sa_dialects = ModuleType("sqlalchemy.dialects")

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

import app.import_export.services as svc  # noqa: E402
from app.import_export.models import ImportJobStatus  # noqa: E402


WS = uuid.uuid4()


def _make_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    return db


def _result(*, scalar=None):
    r = MagicMock()
    r.scalar_one_or_none = MagicMock(return_value=scalar)
    return r


def _make_job(status=ImportJobStatus.uploaded.value):
    job = MagicMock()
    job.id = uuid.uuid4()
    job.workspace_id = WS
    job.status = status
    return job


# ---------------------------------------------------------------------------
# create_job
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_job_stages_row_with_uploaded_status():
    db = _make_db()
    user_id = uuid.uuid4()

    captured = []

    class _ImportJobSpy:
        def __init__(self, **kw):
            captured.append(kw)
            self.id = uuid.uuid4()
            for k, v in kw.items():
                setattr(self, k, v)

    from unittest.mock import patch

    with patch.object(svc, "ImportJob", _ImportJobSpy):
        job = await svc.create_job(
            db,
            workspace_id=WS,
            user_id=user_id,
            format="xlsx",
            source_filename="leads.xlsx",
            upload_size_bytes=12345,
            diff={"rows": []},
        )

    assert len(captured) == 1
    kw = captured[0]
    assert kw["workspace_id"] == WS
    assert kw["user_id"] == user_id
    assert kw["status"] == ImportJobStatus.uploaded.value
    assert kw["format"] == "xlsx"
    assert kw["source_filename"] == "leads.xlsx"
    assert kw["upload_size_bytes"] == 12345
    assert kw["diff_json"] == {"rows": []}
    db.add.assert_called_once()
    db.commit.assert_awaited()


# ---------------------------------------------------------------------------
# get_job
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_job_returns_match():
    db = _make_db()
    job = _make_job()
    db.execute.return_value = _result(scalar=job)

    out = await svc.get_job(db, job_id=job.id, workspace_id=WS)
    assert out is job


@pytest.mark.asyncio
async def test_get_job_raises_for_wrong_workspace():
    """Cross-workspace lookup → 404 (raised as ImportJobNotFound)."""
    db = _make_db()
    db.execute.return_value = _result(scalar=None)

    with pytest.raises(svc.ImportJobNotFound):
        await svc.get_job(db, job_id=uuid.uuid4(), workspace_id=WS)


# ---------------------------------------------------------------------------
# cancel_job
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cancel_job_succeeds_in_uploaded_status():
    db = _make_db()
    job = _make_job(status=ImportJobStatus.uploaded.value)
    db.execute.return_value = _result(scalar=job)

    out = await svc.cancel_job(db, job_id=job.id, workspace_id=WS)
    assert out.status == ImportJobStatus.cancelled.value
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_cancel_job_raises_when_already_running():
    """Once Celery has the job, the manager can't yank it back through
    this endpoint — surface 409 (mapped from ImportJobBadState)."""
    db = _make_db()
    job = _make_job(status=ImportJobStatus.running.value)
    db.execute.return_value = _result(scalar=job)

    with pytest.raises(svc.ImportJobBadState):
        await svc.cancel_job(db, job_id=job.id, workspace_id=WS)


@pytest.mark.asyncio
async def test_cancel_job_raises_when_terminal_status():
    db = _make_db()
    for terminal in (
        ImportJobStatus.succeeded.value,
        ImportJobStatus.failed.value,
        ImportJobStatus.cancelled.value,
    ):
        job = _make_job(status=terminal)
        db.execute.return_value = _result(scalar=job)
        with pytest.raises(svc.ImportJobBadState):
            await svc.cancel_job(db, job_id=job.id, workspace_id=WS)
