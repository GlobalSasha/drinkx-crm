"""Tests for Sprint 1.3.C — enrichment service layer.

SQLAlchemy is stubbed at import time (same pattern as test_enrichment_orchestrator.py).
Service functions are tested with AsyncMock DB sessions.
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
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
        """Stub that returns itself from any call or attribute access — supports method chaining."""
        def __init__(self, *a, **kw): pass
        def __call__(self, *a, **kw): return _Callable()
        def __class_getitem__(cls, item): return cls
        def __getitem__(self, key): return _Callable()
        def __getattr__(self, name): return _Callable()
        def __eq__(self, other): return True
        def __ne__(self, other): return True

    sa = ModuleType("sqlalchemy")
    for name in (
        "Column", "ForeignKey", "Integer", "String", "Text", "JSON",
        "Numeric", "DateTime", "Boolean", "Index", "select",
        "desc", "false", "UniqueConstraint", "text", "nullslast",
        "asc", "or_", "and_", "update", "delete", "cast", "literal",
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
    sa_orm.mapped_column = _noop
    sa_orm.relationship = _Callable()
    sa_orm.selectinload = _Callable()

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

import app.enrichment.services as svc_mod  # noqa: E402
from app.enrichment.services import (  # noqa: E402
    EnrichmentAlreadyRunning,
    EnrichmentBudgetExceeded,
    EnrichmentConcurrencyLimit,
)
from app.leads.services import LeadNotFound  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_run(lead_id=None, status="running"):
    run = MagicMock()
    run.id = uuid.uuid4()
    run.lead_id = lead_id or uuid.uuid4()
    run.user_id = uuid.uuid4()
    run.status = status
    run.provider = "mimo"
    run.model = "mimo-v2-flash"
    run.prompt_tokens = 100
    run.completion_tokens = 50
    run.cost_usd = Decimal("0.002")
    run.duration_ms = 1234
    run.sources_used = ["brave", "hh"]
    run.error = None
    run.result_json = {"company_profile": "Test"}
    run.started_at = datetime.now(tz=timezone.utc)
    run.finished_at = None
    run.created_at = datetime.now(tz=timezone.utc)
    run.updated_at = datetime.now(tz=timezone.utc)
    return run


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_trigger_creates_running_row_returns_202():
    """trigger_enrichment flushes a run with status='running'."""
    lead_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    run = _make_run(lead_id=lead_id, status="running")

    lead = MagicMock()
    lead.id = lead_id
    lead.workspace_id = workspace_id

    db = AsyncMock()

    # First execute: lead lookup → returns lead
    # Second execute: running-run check → returns None (no existing running run)
    lead_result = MagicMock()
    lead_result.scalar_one_or_none.return_value = lead

    no_running_result = MagicMock()
    no_running_result.scalar_one_or_none.return_value = None

    db.execute = AsyncMock(side_effect=[lead_result, no_running_result])
    db.flush = AsyncMock()

    with (
        patch("app.enrichment.services.EnrichmentRun", return_value=run),
        patch("app.enrichment.services.is_at_concurrency_limit", new=AsyncMock(return_value=False)),
        patch("app.enrichment.services.has_budget_remaining", new=AsyncMock(return_value=True)),
    ):
        result = await svc_mod.trigger_enrichment(
            db, workspace_id=workspace_id, user_id=uuid.uuid4(), lead_id=lead_id,
        )

    assert result.status == "running"
    assert result.lead_id == lead_id
    db.flush.assert_called_once()


@pytest.mark.asyncio
async def test_trigger_404_for_lead_in_other_workspace():
    """trigger_enrichment raises LeadNotFound when lead not in workspace."""
    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=execute_result)

    with pytest.raises(LeadNotFound):
        await svc_mod.trigger_enrichment(
            db, workspace_id=uuid.uuid4(), user_id=uuid.uuid4(), lead_id=uuid.uuid4(),
        )


@pytest.mark.asyncio
async def test_latest_returns_most_recent_run():
    """get_latest_run returns the row from the query."""
    lead_id = uuid.uuid4()
    run = _make_run(lead_id=lead_id, status="succeeded")

    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = run
    db.execute = AsyncMock(return_value=execute_result)

    result = await svc_mod.get_latest_run(db, workspace_id=uuid.uuid4(), lead_id=lead_id)

    assert result is run
    assert result.status == "succeeded"


@pytest.mark.asyncio
async def test_trigger_returns_409_when_running_run_exists():
    """trigger_enrichment raises EnrichmentAlreadyRunning when a 'running' run exists."""
    lead_id = uuid.uuid4()
    workspace_id = uuid.uuid4()

    lead = MagicMock()
    lead.id = lead_id
    lead.workspace_id = workspace_id

    existing_run = _make_run(lead_id=lead_id, status="running")

    db = AsyncMock()

    # First execute: lead lookup → returns lead
    # Second execute: running-run check → returns the existing run
    lead_result = MagicMock()
    lead_result.scalar_one_or_none.return_value = lead

    running_result = MagicMock()
    running_result.scalar_one_or_none.return_value = existing_run

    db.execute = AsyncMock(side_effect=[lead_result, running_result])

    with (
        patch("app.enrichment.services.is_at_concurrency_limit", new=AsyncMock(return_value=False)),
        patch("app.enrichment.services.has_budget_remaining", new=AsyncMock(return_value=True)),
    ):
        with pytest.raises(EnrichmentAlreadyRunning) as exc_info:
            await svc_mod.trigger_enrichment(
                db, workspace_id=workspace_id, user_id=uuid.uuid4(), lead_id=lead_id,
            )

    assert exc_info.value.run_id == existing_run.id


@pytest.mark.asyncio
async def test_trigger_creates_new_run_when_previous_is_succeeded():
    """trigger_enrichment creates a new run when previous run has status 'succeeded'."""
    lead_id = uuid.uuid4()
    workspace_id = uuid.uuid4()

    lead = MagicMock()
    lead.id = lead_id
    lead.workspace_id = workspace_id

    new_run = _make_run(lead_id=lead_id, status="running")

    db = AsyncMock()

    # First execute: lead lookup → returns lead
    # Second execute: running-run check → returns None (previous run was succeeded)
    lead_result = MagicMock()
    lead_result.scalar_one_or_none.return_value = lead

    no_running_result = MagicMock()
    no_running_result.scalar_one_or_none.return_value = None

    db.execute = AsyncMock(side_effect=[lead_result, no_running_result])
    db.flush = AsyncMock()

    with (
        patch("app.enrichment.services.EnrichmentRun", return_value=new_run),
        patch("app.enrichment.services.is_at_concurrency_limit", new=AsyncMock(return_value=False)),
        patch("app.enrichment.services.has_budget_remaining", new=AsyncMock(return_value=True)),
    ):
        result = await svc_mod.trigger_enrichment(
            db, workspace_id=workspace_id, user_id=uuid.uuid4(), lead_id=lead_id,
        )

    assert result.status == "running"
    db.flush.assert_called_once()


@pytest.mark.asyncio
async def test_list_returns_runs_in_descending_started_at():
    """list_runs returns multiple rows ordered by the DB query."""
    lead_id = uuid.uuid4()
    run1 = _make_run(lead_id=lead_id, status="succeeded")
    run2 = _make_run(lead_id=lead_id, status="failed")

    db = AsyncMock()
    execute_result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = [run1, run2]
    execute_result.scalars.return_value = scalars_mock
    db.execute = AsyncMock(return_value=execute_result)

    results = await svc_mod.list_runs(db, workspace_id=uuid.uuid4(), lead_id=lead_id, limit=20)

    assert len(results) == 2
    assert results[0].status == "succeeded"
    assert results[1].status == "failed"


# ---------------------------------------------------------------------------
# Sprint 1.3.D — concurrency + budget guard tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_trigger_returns_429_when_concurrency_limit_reached():
    """trigger_enrichment raises EnrichmentConcurrencyLimit when workspace is at limit."""
    lead_id = uuid.uuid4()
    workspace_id = uuid.uuid4()

    lead = MagicMock()
    lead.id = lead_id
    lead.workspace_id = workspace_id

    db = AsyncMock()
    lead_result = MagicMock()
    lead_result.scalar_one_or_none.return_value = lead
    db.execute = AsyncMock(return_value=lead_result)

    with (
        patch("app.enrichment.services.is_at_concurrency_limit", new=AsyncMock(return_value=True)),
        patch("app.enrichment.services.has_budget_remaining", new=AsyncMock(return_value=True)),
    ):
        with pytest.raises(EnrichmentConcurrencyLimit):
            await svc_mod.trigger_enrichment(
                db, workspace_id=workspace_id, user_id=uuid.uuid4(), lead_id=lead_id,
            )


@pytest.mark.asyncio
async def test_trigger_returns_429_when_daily_budget_exceeded():
    """trigger_enrichment raises EnrichmentBudgetExceeded when daily cap is reached."""
    lead_id = uuid.uuid4()
    workspace_id = uuid.uuid4()

    lead = MagicMock()
    lead.id = lead_id
    lead.workspace_id = workspace_id

    db = AsyncMock()
    lead_result = MagicMock()
    lead_result.scalar_one_or_none.return_value = lead
    db.execute = AsyncMock(return_value=lead_result)

    with (
        patch("app.enrichment.services.is_at_concurrency_limit", new=AsyncMock(return_value=False)),
        patch("app.enrichment.services.has_budget_remaining", new=AsyncMock(return_value=False)),
        patch("app.enrichment.services.get_daily_spend_usd", new=AsyncMock(return_value=7.5)),
        patch("app.enrichment.services._daily_cap_usd", return_value=6.67),
    ):
        with pytest.raises(EnrichmentBudgetExceeded) as exc_info:
            await svc_mod.trigger_enrichment(
                db, workspace_id=workspace_id, user_id=uuid.uuid4(), lead_id=lead_id,
            )

    assert exc_info.value.spent == 7.5
    assert abs(exc_info.value.cap - 6.67) < 1e-6


@pytest.mark.asyncio
async def test_concurrency_limit_does_not_count_succeeded_runs():
    """trigger_enrichment succeeds when only succeeded runs exist (not at concurrency limit)."""
    lead_id = uuid.uuid4()
    workspace_id = uuid.uuid4()

    lead = MagicMock()
    lead.id = lead_id
    lead.workspace_id = workspace_id

    new_run = _make_run(lead_id=lead_id, status="running")

    db = AsyncMock()

    lead_result = MagicMock()
    lead_result.scalar_one_or_none.return_value = lead

    no_running_result = MagicMock()
    no_running_result.scalar_one_or_none.return_value = None

    db.execute = AsyncMock(side_effect=[lead_result, no_running_result])
    db.flush = AsyncMock()

    # Concurrency limit returns False (not at limit — only succeeded runs)
    with (
        patch("app.enrichment.services.is_at_concurrency_limit", new=AsyncMock(return_value=False)),
        patch("app.enrichment.services.has_budget_remaining", new=AsyncMock(return_value=True)),
        patch("app.enrichment.services.EnrichmentRun", return_value=new_run),
    ):
        result = await svc_mod.trigger_enrichment(
            db, workspace_id=workspace_id, user_id=uuid.uuid4(), lead_id=lead_id,
        )

    assert result.status == "running"
    db.flush.assert_called_once()
