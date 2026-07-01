"""Tests for plan 015 — automation step reliability.

Mock-only — same sqlalchemy stub pattern as test_automation_multistep.py /
test_automation_builder_service.py. Covers:

  1. A transient step failure (EmailSendError) stays `pending` and bumps
     `attempt_count`, with `scheduled_at` pushed into the future.
  2. After `_MAX_STEP_ATTEMPTS` transient failures, the step becomes
     `failed` instead of retrying again.
  3. A terminal failure (ValueError — e.g. missing config) is `failed`
     immediately, with no retry regardless of `attempt_count`.
  4. `rerun_run` resets a failed run's failed step rows to `pending` and
     flips the parent run row back to `queued`.
  5. `rerun_run` raises `RunNotFound` for a cross-workspace / unknown run.
  6. `test_fire` executes the automation's step 0 against the chosen
     lead and writes success run/step rows without going through
     `evaluate_trigger`'s condition/trigger-matching fan-out.
  7. `test_fire` raises `LeadNotFound` when the lead isn't in the
     workspace.
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# sqlalchemy stub — same as test_automation_multistep.py, plus
# OperationalError (services.py now imports it for transient-error
# classification).
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

    class _OperationalError(Exception):
        pass

    sa_exc.IntegrityError = _IntegrityError
    sa_exc.OperationalError = _OperationalError

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

from app.automation_builder import services as svc  # noqa: E402
from app.email.sender import EmailSendError  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

WS = uuid.uuid4()
LEAD_ID = uuid.uuid4()


def _make_lead(**kw):
    lead = MagicMock()
    lead.id = kw.get("id", LEAD_ID)
    lead.workspace_id = WS
    lead.priority = kw.get("priority", "A")
    lead.score = kw.get("score", 75)
    lead.deal_type = kw.get("deal_type", "enterprise_direct")
    lead.stage_id = kw.get("stage_id", uuid.uuid4())
    lead.pipeline_id = kw.get("pipeline_id", uuid.uuid4())
    lead.source = None
    lead.assignment_status = "pool"
    lead.company_name = kw.get("company_name", "Acme Corp")
    lead.city = "Moscow"
    lead.email = kw.get("email", None)
    lead.phone = None
    lead.website = None
    lead.segment = None
    lead.next_step = None
    lead.blocker = None
    return lead


def _make_automation(**kw):
    a = MagicMock()
    a.id = kw.get("id", uuid.uuid4())
    a.workspace_id = WS
    a.name = kw.get("name", "Test")
    a.trigger = kw.get("trigger", "stage_change")
    a.trigger_config_json = kw.get("trigger_config_json", None)
    a.condition_json = kw.get("condition_json", None)
    a.action_type = kw.get("action_type", "create_task")
    a.action_config_json = kw.get(
        "action_config_json", {"title": "Test task"}
    )
    a.steps_json = kw.get("steps_json", None)
    a.is_active = True
    return a


def _make_step_run(**kw):
    s = MagicMock()
    s.id = kw.get("id", uuid.uuid4())
    s.automation_run_id = kw.get("automation_run_id", uuid.uuid4())
    s.lead_id = kw.get("lead_id", LEAD_ID)
    s.step_index = kw.get("step_index", 1)
    s.step_json = kw.get(
        "step_json", {"type": "create_task", "config": {"title": "Followup"}}
    )
    s.scheduled_at = kw.get(
        "scheduled_at", datetime.now(tz=timezone.utc) - timedelta(minutes=10)
    )
    s.executed_at = kw.get("executed_at", None)
    s.status = kw.get("status", "pending")
    s.error = kw.get("error", None)
    s.attempt_count = kw.get("attempt_count", 0)
    return s


class _AsyncCM:
    async def __aenter__(self): return self
    async def __aexit__(self, *_): return False


class _RaisingAsyncCM:
    """Async CM whose __aexit__ propagates an exception raised inside
    the `async with` block — mirrors `db.begin_nested()` unwinding when
    `_dispatch_step` raises."""
    def __init__(self, exc: Exception):
        self._exc = exc

    async def __aenter__(self):
        raise self._exc

    async def __aexit__(self, *_):
        return False


# ===========================================================================
# 1. Transient step failure stays pending + bumps attempt_count
# ===========================================================================

@pytest.mark.asyncio
async def test_transient_failure_retries_with_backoff():
    """An EmailSendError (transient) leaves the row `pending`, bumps
    `attempt_count`, and pushes `scheduled_at` into the future so the
    next beat tick doesn't immediately re-hit the same failure."""
    step_run = _make_step_run(attempt_count=0)
    original_scheduled_at = step_run.scheduled_at

    parent_run = MagicMock()
    parent_run.automation_id = uuid.uuid4()

    lead = _make_lead()

    async def fake_list_due(_db, **kw):
        return [step_run]

    lead_result = MagicMock()
    lead_result.scalar_one_or_none = MagicMock(return_value=lead)
    parent_result = MagicMock()
    parent_result.scalar_one_or_none = MagicMock(return_value=parent_run)

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[lead_result, parent_result])
    db.begin_nested = MagicMock(
        return_value=_RaisingAsyncCM(EmailSendError("smtp timeout"))
    )
    db.commit = AsyncMock()

    with patch(
        "app.automation_builder.repositories.list_due_step_runs",
        new=fake_list_due,
    ):
        result = await svc.execute_due_step_runs(db)

    assert step_run.status == "pending"
    assert step_run.executed_at is None
    assert step_run.attempt_count == 1
    assert step_run.scheduled_at > original_scheduled_at
    assert result["scanned"] == 1
    assert result["fired"] == 0
    assert result["failed"] == 0
    assert result["retried"] == 1


# ===========================================================================
# 2. After _MAX_STEP_ATTEMPTS, a transient failure becomes terminal
# ===========================================================================

@pytest.mark.asyncio
async def test_transient_failure_becomes_failed_after_max_attempts():
    """Once `attempt_count` has already reached `_MAX_STEP_ATTEMPTS`,
    another transient failure is terminal — no infinite retry."""
    step_run = _make_step_run(attempt_count=svc._MAX_STEP_ATTEMPTS)

    parent_run = MagicMock()
    parent_run.automation_id = uuid.uuid4()
    lead = _make_lead()

    async def fake_list_due(_db, **kw):
        return [step_run]

    lead_result = MagicMock()
    lead_result.scalar_one_or_none = MagicMock(return_value=lead)
    parent_result = MagicMock()
    parent_result.scalar_one_or_none = MagicMock(return_value=parent_run)

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[lead_result, parent_result])
    db.begin_nested = MagicMock(
        return_value=_RaisingAsyncCM(EmailSendError("smtp timeout"))
    )
    db.commit = AsyncMock()

    with patch(
        "app.automation_builder.repositories.list_due_step_runs",
        new=fake_list_due,
    ):
        result = await svc.execute_due_step_runs(db)

    assert step_run.status == "failed"
    assert step_run.executed_at is not None
    assert result["fired"] == 0
    assert result["failed"] == 1
    assert result["retried"] == 0


# ===========================================================================
# 3. A terminal (non-transient) failure never retries
# ===========================================================================

@pytest.mark.asyncio
async def test_terminal_failure_does_not_retry():
    """A ValueError (bad config — e.g. missing template) is `failed`
    immediately regardless of `attempt_count`, even on the very first
    attempt. Also covers `OperationalError` NOT being conflated with
    unrelated exception types — only the classified set retries."""
    step_run = _make_step_run(attempt_count=0)

    parent_run = MagicMock()
    parent_run.automation_id = uuid.uuid4()
    lead = _make_lead()

    async def fake_list_due(_db, **kw):
        return [step_run]

    lead_result = MagicMock()
    lead_result.scalar_one_or_none = MagicMock(return_value=lead)
    parent_result = MagicMock()
    parent_result.scalar_one_or_none = MagicMock(return_value=parent_run)

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[lead_result, parent_result])
    db.begin_nested = MagicMock(
        return_value=_RaisingAsyncCM(ValueError("create_task missing title"))
    )
    db.commit = AsyncMock()

    with patch(
        "app.automation_builder.repositories.list_due_step_runs",
        new=fake_list_due,
    ):
        result = await svc.execute_due_step_runs(db)

    assert step_run.status == "failed"
    assert step_run.executed_at is not None
    assert step_run.attempt_count == 0
    assert result["fired"] == 0
    assert result["failed"] == 1
    assert result["retried"] == 0


def test_operational_error_is_classified_transient():
    """Sanity check on the classifier itself — both documented
    transient types are recognised."""
    assert svc._is_transient_step_error(EmailSendError("x")) is True
    assert svc._is_transient_step_error(OperationalError("x", None, None)) is True
    assert svc._is_transient_step_error(ValueError("x")) is False


# ===========================================================================
# 4. rerun_run resets failed steps + parent run status
# ===========================================================================

@pytest.mark.asyncio
async def test_rerun_run_resets_failed_steps_to_pending():
    automation = _make_automation(
        action_type="create_task",
        action_config_json={"title": "Legacy task"},
        steps_json=None,
    )
    run = MagicMock()
    run.id = uuid.uuid4()
    run.automation_id = automation.id
    run.lead_id = LEAD_ID
    run.status = "failed"
    run.error = "boom"

    failed_step = _make_step_run(
        automation_run_id=run.id,
        step_index=0,
        status="failed",
        error="boom",
        executed_at=datetime.now(tz=timezone.utc),
        attempt_count=2,
    )

    async def fake_get_run_by_id(_db, **kw):
        return run

    async def fake_get_automation(_db, **kw):
        return automation

    async def fake_list_step_runs(_db, **kw):
        return [failed_step]

    db = AsyncMock()

    with patch(
        "app.automation_builder.repositories.get_run_by_id",
        new=fake_get_run_by_id,
    ), patch(
        "app.automation_builder.repositories.get_by_id",
        new=fake_get_automation,
    ), patch(
        "app.automation_builder.repositories.list_step_runs_for_run",
        new=fake_list_step_runs,
    ):
        result = await svc.rerun_run(db, workspace_id=WS, run_id=run.id)

    assert failed_step.status == "pending"
    assert failed_step.error is None
    assert failed_step.executed_at is None
    assert failed_step.attempt_count == 0
    assert result.status == "queued"
    assert result.error is None


# ===========================================================================
# 5. rerun_run raises RunNotFound for unknown/cross-workspace run
# ===========================================================================

@pytest.mark.asyncio
async def test_rerun_run_raises_not_found():
    async def fake_get_run_by_id(_db, **kw):
        return None

    db = AsyncMock()

    with patch(
        "app.automation_builder.repositories.get_run_by_id",
        new=fake_get_run_by_id,
    ):
        with pytest.raises(svc.RunNotFound):
            await svc.rerun_run(db, workspace_id=WS, run_id=uuid.uuid4())


# ===========================================================================
# 6. test_fire executes step 0 against the chosen lead
# ===========================================================================

@pytest.mark.asyncio
async def test_test_fire_executes_step0_and_records_success():
    """test_fire dispatches the automation's step 0 against the given
    lead directly — no trigger matching, no condition_json evaluation,
    no fan-out over other automations."""
    automation = _make_automation(
        # A condition that would normally reject this lead — test_fire
        # must NOT evaluate it (that's the whole point of a test fire).
        condition_json={"all": [{"field": "priority", "op": "eq", "value": "Z"}]},
        steps_json=[
            {"type": "create_task", "config": {"title": "Step 0"}},
            {"type": "delay_hours", "config": {"hours": 24}},
            {"type": "create_task", "config": {"title": "Step 2"}},
        ],
    )
    lead = _make_lead()

    runs: list[dict] = []
    step_rows: list[dict] = []

    async def fake_get_automation(_db, **kw):
        return automation

    async def fake_create_run(_db, **kw):
        runs.append(kw)
        m = MagicMock()
        m.id = uuid.uuid4()
        m.status = kw["status"]
        m.error = kw.get("error")
        return m

    async def fake_create_step_run(_db, **kw):
        step_rows.append(kw)
        return MagicMock()

    lead_result = MagicMock()
    lead_result.scalar_one_or_none = MagicMock(return_value=lead)

    db = AsyncMock()
    db.execute = AsyncMock(return_value=lead_result)
    db.begin_nested = MagicMock(return_value=_AsyncCM())

    with patch(
        "app.automation_builder.repositories.get_by_id",
        new=fake_get_automation,
    ), patch(
        "app.automation_builder.repositories.create_run",
        new=fake_create_run,
    ), patch(
        "app.automation_builder.repositories.create_step_run",
        new=fake_create_step_run,
    ), patch(
        "app.automation_builder.services.Activity", new=MagicMock
    ):
        result = await svc.test_fire(
            db,
            workspace_id=WS,
            automation_id=automation.id,
            lead_id=lead.id,
        )

    assert result.status == "success"
    assert len(runs) == 1
    assert runs[0]["status"] == "success"

    # Step 0 executed synchronously; step 2 scheduled ~24h out; the
    # delay step itself never gets a queue row.
    assert len(step_rows) == 2
    sr0 = next(r for r in step_rows if r["step_index"] == 0)
    sr2 = next(r for r in step_rows if r["step_index"] == 2)
    assert sr0["status"] == "success"
    assert sr0["executed_at"] is not None
    assert sr2["status"] == "pending"
    assert sr2["executed_at"] is None


# ===========================================================================
# 7. test_fire raises LeadNotFound for a lead outside the workspace
# ===========================================================================

@pytest.mark.asyncio
async def test_test_fire_raises_lead_not_found():
    automation = _make_automation()

    async def fake_get_automation(_db, **kw):
        return automation

    lead_result = MagicMock()
    lead_result.scalar_one_or_none = MagicMock(return_value=None)

    db = AsyncMock()
    db.execute = AsyncMock(return_value=lead_result)

    with patch(
        "app.automation_builder.repositories.get_by_id",
        new=fake_get_automation,
    ):
        with pytest.raises(svc.LeadNotFound):
            await svc.test_fire(
                db,
                workspace_id=WS,
                automation_id=automation.id,
                lead_id=uuid.uuid4(),
            )
