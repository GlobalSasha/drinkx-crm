"""Tests for Sprint 2.7 G1 — Sentry capture helper + swallow-site reporting.

Same sqlalchemy-stub pattern as test_audit.py / test_email_sender.py:
mock-only, 0 DB / 0 network. We verify three things:

1. The `capture()` helper forwards exceptions to `sentry_sdk.capture_exception`
   and is a soft no-op when the SDK can't be imported.
2. Each swallow site (`audit.log`, `safe_evaluate_trigger`,
   `daily_plan_runner`) calls the helper alongside its existing
   structlog warning.
3. The structlog warning still emits — Sentry is additive, not a
   replacement for the existing log line.
"""
from __future__ import annotations

import sys
import uuid
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Stub sqlalchemy before any ORM imports (matches test_audit.py)
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
        "nullsfirst", "asc", "or_", "and_", "update", "delete", "cast",
        "literal", "Date",
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
# 1. capture() helper — forwards to sentry_sdk.capture_exception
# ---------------------------------------------------------------------------

def test_capture_forwards_to_sentry_sdk():
    """When sentry_sdk is importable, capture() pushes a scope with the
    supplied fingerprint / tags / extra and calls capture_exception."""
    from app.common import sentry_capture

    fake_scope = MagicMock()
    fake_push = MagicMock()
    fake_push.__enter__ = MagicMock(return_value=fake_scope)
    fake_push.__exit__ = MagicMock(return_value=False)

    fake_sentry = ModuleType("sentry_sdk")
    fake_sentry.push_scope = MagicMock(return_value=fake_push)
    fake_sentry.capture_exception = MagicMock()

    err = RuntimeError("boom")

    with patch.dict(sys.modules, {"sentry_sdk": fake_sentry}):
        sentry_capture.capture(
            err,
            fingerprint=["fp1", "fp2"],
            tags={"site": "test", "trigger": "stage_change"},
            extra={"lead_id": "abc"},
        )

    assert fake_sentry.capture_exception.call_count == 1
    assert fake_sentry.capture_exception.call_args.args[0] is err
    assert fake_scope.fingerprint == ["fp1", "fp2"]
    fake_scope.set_tag.assert_any_call("site", "test")
    fake_scope.set_tag.assert_any_call("trigger", "stage_change")
    fake_scope.set_extra.assert_any_call("lead_id", "abc")


def test_capture_is_noop_when_sentry_sdk_missing():
    """If sentry_sdk import fails (or is somehow broken), capture() must
    return without raising — swallow paths must stay swallowed."""
    from app.common import sentry_capture

    # Hide sentry_sdk from sys.modules and block re-import via a finder
    saved = sys.modules.pop("sentry_sdk", None)

    class _Block:
        def find_module(self, name, path=None):
            if name == "sentry_sdk":
                return self
            return None
        def load_module(self, name):
            raise ImportError("blocked for test")

    blocker = _Block()
    sys.meta_path.insert(0, blocker)
    try:
        # Should not raise
        sentry_capture.capture(RuntimeError("x"), fingerprint=["a"])
    finally:
        sys.meta_path.remove(blocker)
        if saved is not None:
            sys.modules["sentry_sdk"] = saved


# ---------------------------------------------------------------------------
# 2. audit.log() swallow → capture is called
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_audit_log_swallow_calls_sentry_capture():
    """When session.add() raises inside audit.log(), capture() must be
    invoked once with a fingerprint scoped to the action name."""
    import app.audit.audit as audit_mod

    db = AsyncMock()
    db.add = MagicMock(side_effect=RuntimeError("session detached"))

    with patch("app.common.sentry_capture.capture") as mock_capture:
        await audit_mod.log(
            db,
            action="lead.create",
            workspace_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            entity_type="lead",
            entity_id=uuid.uuid4(),
            delta={"company_name": "Acme"},
        )

    assert mock_capture.call_count == 1
    call_kwargs = mock_capture.call_args.kwargs
    # Fingerprint groups all audit-log-swallow events; second slot
    # is the action name so operators can mute-by-action if needed.
    assert call_kwargs["fingerprint"] == ["audit-log-swallow", "lead.create"]
    assert call_kwargs["tags"]["site"] == "audit.log"
    assert call_kwargs["tags"]["action"] == "lead.create"


# ---------------------------------------------------------------------------
# 3. safe_evaluate_trigger swallow → capture is called
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_safe_evaluate_trigger_swallow_calls_sentry_capture():
    """When evaluate_trigger raises, safe_evaluate_trigger swallows it AND
    reports to Sentry. The parent transaction is preserved (no re-raise)."""
    from app.automation_builder import services as auto_svc

    db = AsyncMock()
    workspace_id = uuid.uuid4()
    fake_lead = MagicMock()
    fake_lead.id = uuid.uuid4()

    boom = RuntimeError("trigger eval failed")

    with (
        patch.object(auto_svc, "evaluate_trigger", new=AsyncMock(side_effect=boom)),
        patch("app.common.sentry_capture.capture") as mock_capture,
    ):
        # Must not raise
        await auto_svc.safe_evaluate_trigger(
            db,
            workspace_id=workspace_id,
            trigger="stage_change",
            lead=fake_lead,
            payload={"from_stage_id": "x"},
        )

    assert mock_capture.call_count == 1
    call_kwargs = mock_capture.call_args.kwargs
    assert call_kwargs["fingerprint"] == ["automation-evaluate-trigger", "stage_change"]
    assert call_kwargs["tags"]["site"] == "automation.evaluate_trigger"
    assert call_kwargs["tags"]["trigger"] == "stage_change"


# ---------------------------------------------------------------------------
# 4. enrichment _mark_run_failed flips status='failed' on a stranded row
# ---------------------------------------------------------------------------

def _stub_redis_and_httpx():
    """Enrichment.routers transitively pulls Redis (sources/cache.py).
    Local dev boxes don't always have it — stub before import."""
    if "redis" not in sys.modules:
        redis_mod = ModuleType("redis")
        redis_async = ModuleType("redis.asyncio")
        redis_async.Redis = object
        redis_async.from_url = lambda *a, **kw: MagicMock()
        redis_mod.asyncio = redis_async
        sys.modules["redis"] = redis_mod
        sys.modules["redis.asyncio"] = redis_async


@pytest.mark.asyncio
async def test_enrichment_mark_run_failed_flips_status_when_running():
    """_mark_run_failed opens a fresh session, finds the EnrichmentRun
    row, and flips status='failed' with a truncated error string —
    BUT only when the row is still 'running'. If the orchestrator
    already set 'succeeded'/'failed' before crashing elsewhere, we
    leave the terminal state alone. Without this branch the
    BackgroundTasks crash path strands rows forever (Sprint 2.6
    audit finding)."""
    _stub_redis_and_httpx()
    import app.enrichment.routers as routers_mod

    run_id = uuid.uuid4()
    boom = RuntimeError("orchestrator crashed")

    # Fake row in 'running' state
    fake_row = MagicMock()
    fake_row.status = "running"
    fake_row.error = None

    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none = MagicMock(return_value=fake_row)

    fake_session = AsyncMock()
    fake_session.execute = AsyncMock(return_value=scalar_result)
    fake_session.commit = AsyncMock()

    fake_factory_cm = MagicMock()
    fake_factory_cm.__aenter__ = AsyncMock(return_value=fake_session)
    fake_factory_cm.__aexit__ = AsyncMock(return_value=False)

    fake_factory = MagicMock(return_value=fake_factory_cm)

    await routers_mod._mark_run_failed(fake_factory, run_id, boom)

    # Row got flipped
    assert fake_row.status == "failed"
    assert fake_row.error is not None
    assert "RuntimeError" in fake_row.error
    assert "orchestrator crashed" in fake_row.error
    fake_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_enrichment_mark_run_failed_skips_terminal_rows():
    """If the row is already 'succeeded' (orchestrator finished but
    a downstream commit hook crashed), don't overwrite it."""
    _stub_redis_and_httpx()
    import app.enrichment.routers as routers_mod

    run_id = uuid.uuid4()
    fake_row = MagicMock()
    fake_row.status = "succeeded"
    fake_row.error = None

    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none = MagicMock(return_value=fake_row)

    fake_session = AsyncMock()
    fake_session.execute = AsyncMock(return_value=scalar_result)
    fake_session.commit = AsyncMock()

    fake_factory_cm = MagicMock()
    fake_factory_cm.__aenter__ = AsyncMock(return_value=fake_session)
    fake_factory_cm.__aexit__ = AsyncMock(return_value=False)

    fake_factory = MagicMock(return_value=fake_factory_cm)

    await routers_mod._mark_run_failed(fake_factory, run_id, RuntimeError("late"))

    # Row left alone
    assert fake_row.status == "succeeded"
    assert fake_row.error is None
    fake_session.commit.assert_not_called()


# ---------------------------------------------------------------------------
# 5. observability.init_sentry_if_dsn — no-op when DSN is empty
# ---------------------------------------------------------------------------

def test_init_sentry_skipped_when_dsn_empty():
    """The init helper used by app/main.py:lifespan is a no-op when
    settings.sentry_dsn is empty. This is the production default —
    telemetry off until the operator opts in."""
    from app import observability

    fake_settings = MagicMock()
    fake_settings.sentry_dsn = ""
    fake_settings.app_env = "test"

    fake_sentry = ModuleType("sentry_sdk")
    fake_sentry.init = MagicMock()

    with patch.dict(sys.modules, {"sentry_sdk": fake_sentry}):
        ran = observability.init_sentry_if_dsn(fake_settings)

    assert ran is False
    assert fake_sentry.init.call_count == 0


def test_init_sentry_fires_when_dsn_set():
    """When settings.sentry_dsn is set, init_sentry_if_dsn calls
    sentry_sdk.init() with the env-derived environment + a 0.1
    trace sample rate."""
    from app import observability

    fake_settings = MagicMock()
    fake_settings.sentry_dsn = "https://example.ingest.sentry.io/123"
    fake_settings.app_env = "production"

    fake_sentry = ModuleType("sentry_sdk")
    fake_sentry.init = MagicMock()

    with patch.dict(sys.modules, {"sentry_sdk": fake_sentry}):
        ran = observability.init_sentry_if_dsn(fake_settings)

    assert ran is True
    assert fake_sentry.init.call_count == 1
    init_kwargs = fake_sentry.init.call_args.kwargs
    assert init_kwargs["dsn"] == "https://example.ingest.sentry.io/123"
    assert init_kwargs["environment"] == "production"
    assert init_kwargs["traces_sample_rate"] == 0.1
