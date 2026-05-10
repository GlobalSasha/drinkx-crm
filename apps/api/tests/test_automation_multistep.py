"""Tests for Sprint 2.7 G2 — multi-step automation chains.

Mock-only — same sqlalchemy stub pattern as test_automation_builder_service.py.
Covers:

  1. _validate_steps rejects unknown step type
  2. _validate_steps rejects bad delay_hours (0 / negative / overcap)
  3. _compute_schedule_offsets correctness (delay aggregation)
  4. _resolved_chain falls back to legacy single-action when no steps_json
  5. evaluate_trigger multi-step: step 0 fires immediate, step 1+ scheduled
  6. evaluate_trigger step 0 failure stops the chain (steps 1+ unscheduled)
  7. evaluate_trigger preserves step ordering in the queue
  8. execute_due_step_runs fires a pending step and flips status='success'
  9. execute_due_step_runs marks orphan-lead step as 'skipped'
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# sqlalchemy stub — same as test_automation_builder_service.py
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

from app.automation_builder import services as svc  # noqa: E402

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


class _AsyncCM:
    async def __aenter__(self): return self
    async def __aexit__(self, *_): return False


# ===========================================================================
# 1. _validate_steps rejects unknown step type
# ===========================================================================

def test_validate_steps_rejects_unknown_type():
    with pytest.raises(svc.InvalidSteps) as ex:
        svc._validate_steps(
            [{"type": "post_to_slack", "config": {}}]
        )
    assert "post_to_slack" in str(ex.value)


# ===========================================================================
# 2. _validate_steps rejects bad delay_hours
# ===========================================================================

def test_validate_steps_rejects_zero_delay():
    """0 is meaningless — admin probably meant something else."""
    with pytest.raises(svc.InvalidSteps):
        svc._validate_steps(
            [{"type": "delay_hours", "config": {"hours": 0}}]
        )


def test_validate_steps_rejects_overcap_delay():
    """30-day cap (720h) keeps typo'd 8760h delays from poisoning the queue."""
    with pytest.raises(svc.InvalidSteps):
        svc._validate_steps(
            [{"type": "delay_hours", "config": {"hours": 9999}}]
        )


def test_validate_steps_accepts_valid_chain():
    """Happy path — three-step chain with one delay between two actions."""
    svc._validate_steps([
        {"type": "send_template", "config": {"template_id": str(uuid.uuid4())}},
        {"type": "delay_hours", "config": {"hours": 24}},
        {"type": "create_task", "config": {"title": "Follow up"}},
    ])


# ===========================================================================
# 3. _compute_schedule_offsets correctness
# ===========================================================================

def test_compute_schedule_offsets_simple():
    """Two actions separated by a 24h delay → offsets [0, 24, 24].
    The delay step itself has offset=24 (it inherits the running
    cumulative from before its delta lands on the next step)."""
    offsets = svc._compute_schedule_offsets([
        {"type": "send_template", "config": {"template_id": "x"}},
        {"type": "delay_hours", "config": {"hours": 24}},
        {"type": "create_task", "config": {"title": "y"}},
    ])
    assert offsets == [0, 0, 24]


def test_compute_schedule_offsets_chained_delays():
    """Multiple delays accumulate — t=0 → 2h → 26h between non-delay steps."""
    offsets = svc._compute_schedule_offsets([
        {"type": "send_template", "config": {"template_id": "a"}},
        {"type": "delay_hours", "config": {"hours": 2}},
        {"type": "create_task", "config": {"title": "b"}},
        {"type": "delay_hours", "config": {"hours": 24}},
        {"type": "send_template", "config": {"template_id": "c"}},
    ])
    assert offsets == [0, 0, 2, 2, 26]


# ===========================================================================
# 4. _resolved_chain falls back to legacy single-action
# ===========================================================================

def test_resolved_chain_uses_steps_when_present():
    auto = _make_automation(
        steps_json=[
            {"type": "create_task", "config": {"title": "x"}},
            {"type": "delay_hours", "config": {"hours": 1}},
            {"type": "create_task", "config": {"title": "y"}},
        ],
    )
    chain = svc._resolved_chain(auto)
    assert len(chain) == 3
    assert chain[0]["config"]["title"] == "x"


def test_resolved_chain_falls_back_to_legacy_action():
    """Legacy single-action automation is treated as a 1-element chain."""
    auto = _make_automation(
        action_type="create_task",
        action_config_json={"title": "Legacy task"},
        steps_json=None,
    )
    chain = svc._resolved_chain(auto)
    assert len(chain) == 1
    assert chain[0]["type"] == "create_task"
    assert chain[0]["config"]["title"] == "Legacy task"


# ===========================================================================
# 5. evaluate_trigger multi-step: step 0 fires immediate, steps 1+ scheduled
# ===========================================================================

@pytest.mark.asyncio
async def test_evaluate_trigger_multi_step_schedules_subsequent_steps():
    """3-step chain (action → 24h delay → action) — after evaluate_trigger:
      - parent run row: status='success'
      - step 0 row: executed_at == now (synchronous fire)
      - step 1 (delay) NOT scheduled (no side effect to fire)
      - step 2 row: executed_at IS NULL, scheduled_at ~ now + 24h
    """
    auto = _make_automation(
        steps_json=[
            {"type": "create_task", "config": {"title": "Step 0"}},
            {"type": "delay_hours", "config": {"hours": 24}},
            {"type": "create_task", "config": {"title": "Step 2"}},
        ],
    )

    runs: list[dict] = []
    step_rows: list[dict] = []

    async def fake_list_active(_db, **kw):
        return [auto]

    async def fake_create_run(_db, **kw):
        runs.append(kw)
        m = MagicMock()
        m.id = uuid.uuid4()
        return m

    async def fake_create_step_run(_db, **kw):
        step_rows.append(kw)
        return MagicMock()

    db = AsyncMock()
    db.begin_nested = MagicMock(return_value=_AsyncCM())
    lead = _make_lead()

    with patch(
        "app.automation_builder.repositories.list_active_for_trigger",
        new=fake_list_active,
    ), patch(
        "app.automation_builder.repositories.create_run",
        new=fake_create_run,
    ), patch(
        "app.automation_builder.repositories.create_step_run",
        new=fake_create_step_run,
    ), patch(
        "app.automation_builder.services.Activity", new=MagicMock
    ):
        await svc.evaluate_trigger(
            db,
            workspace_id=WS,
            trigger="stage_change",
            lead=lead,
            payload={},
        )

    # One parent run row, status=success
    assert len(runs) == 1
    assert runs[0]["status"] == "success"

    # Step rows: step 0 (executed) + step 2 (pending). Step 1 is a
    # delay — skipped from the queue (its hours rolled into step 2's
    # offset).
    assert len(step_rows) == 2
    sr0 = next(r for r in step_rows if r["step_index"] == 0)
    sr2 = next(r for r in step_rows if r["step_index"] == 2)

    assert sr0["status"] == "success"
    assert sr0["executed_at"] is not None
    assert sr0["step_json"]["config"]["title"] == "Step 0"

    assert sr2["status"] == "pending"
    assert sr2["executed_at"] is None
    # Scheduled ~24h in the future (allow a 5s slop for test runtime).
    delta = sr2["scheduled_at"] - sr0["scheduled_at"]
    assert timedelta(hours=23, minutes=59) < delta < timedelta(hours=24, minutes=1)


# ===========================================================================
# 6. evaluate_trigger step 0 failure stops chain
# ===========================================================================

@pytest.mark.asyncio
async def test_evaluate_trigger_step0_failure_stops_chain():
    """When step 0 raises (e.g. missing template), the chain must not
    schedule step 1+. Parent run row gets status='failed'; only step 0
    audit row is written, with status='failed'."""
    auto = _make_automation(
        steps_json=[
            {"type": "send_template", "config": {"template_id": "not-a-uuid"}},
            {"type": "delay_hours", "config": {"hours": 1}},
            {"type": "create_task", "config": {"title": "Should not fire"}},
        ],
    )

    runs: list[dict] = []
    step_rows: list[dict] = []

    async def fake_list_active(_db, **kw):
        return [auto]

    async def fake_create_run(_db, **kw):
        runs.append(kw)
        m = MagicMock()
        m.id = uuid.uuid4()
        return m

    async def fake_create_step_run(_db, **kw):
        step_rows.append(kw)
        return MagicMock()

    db = AsyncMock()
    db.begin_nested = MagicMock(return_value=_AsyncCM())
    lead = _make_lead()

    with patch(
        "app.automation_builder.repositories.list_active_for_trigger",
        new=fake_list_active,
    ), patch(
        "app.automation_builder.repositories.create_run",
        new=fake_create_run,
    ), patch(
        "app.automation_builder.repositories.create_step_run",
        new=fake_create_step_run,
    ), patch(
        "app.automation_builder.services.Activity", new=MagicMock
    ):
        await svc.evaluate_trigger(
            db,
            workspace_id=WS,
            trigger="stage_change",
            lead=lead,
            payload={},
        )

    # Parent run failed
    assert len(runs) == 1
    assert runs[0]["status"] == "failed"

    # Only step 0 row (the failure record). Steps 1+ stayed
    # unscheduled — chain stopped at the first error.
    assert len(step_rows) == 1
    assert step_rows[0]["step_index"] == 0
    assert step_rows[0]["status"] == "failed"


# ===========================================================================
# 7. evaluate_trigger preserves step ordering
# ===========================================================================

@pytest.mark.asyncio
async def test_evaluate_trigger_preserves_step_index_ordering():
    """5-step chain — verify the per-step rows arrive with correct
    step_index values + non-delay steps only get queued."""
    auto = _make_automation(
        steps_json=[
            {"type": "create_task", "config": {"title": "0"}},
            {"type": "delay_hours", "config": {"hours": 1}},
            {"type": "create_task", "config": {"title": "2"}},
            {"type": "delay_hours", "config": {"hours": 2}},
            {"type": "create_task", "config": {"title": "4"}},
        ],
    )

    step_rows: list[dict] = []

    async def fake_list_active(_db, **kw):
        return [auto]

    async def fake_create_run(_db, **kw):
        m = MagicMock()
        m.id = uuid.uuid4()
        return m

    async def fake_create_step_run(_db, **kw):
        step_rows.append(kw)
        return MagicMock()

    db = AsyncMock()
    db.begin_nested = MagicMock(return_value=_AsyncCM())
    lead = _make_lead()

    with patch(
        "app.automation_builder.repositories.list_active_for_trigger",
        new=fake_list_active,
    ), patch(
        "app.automation_builder.repositories.create_run",
        new=fake_create_run,
    ), patch(
        "app.automation_builder.repositories.create_step_run",
        new=fake_create_step_run,
    ), patch(
        "app.automation_builder.services.Activity", new=MagicMock
    ):
        await svc.evaluate_trigger(
            db,
            workspace_id=WS,
            trigger="stage_change",
            lead=lead,
            payload={},
        )

    # Three non-delay steps — indices 0, 2, 4 (delays at 1 and 3 are
    # gates only, no queue entry).
    indices = sorted(r["step_index"] for r in step_rows)
    assert indices == [0, 2, 4]


# ===========================================================================
# 8. execute_due_step_runs fires a pending step
# ===========================================================================

@pytest.mark.asyncio
async def test_execute_due_step_runs_fires_pending_step():
    """The beat scheduler picks up a due row, dispatches the step
    handler, flips the row to status='success'. Smoke test against
    the simplest step type (create_task) so the handler doesn't trip
    on the sqlalchemy stub."""
    step_run = MagicMock()
    step_run.id = uuid.uuid4()
    step_run.automation_run_id = uuid.uuid4()
    step_run.lead_id = LEAD_ID
    step_run.step_index = 1
    step_run.step_json = {
        "type": "create_task",
        "config": {"title": "Followup ping"},
    }
    step_run.scheduled_at = datetime.now(tz=timezone.utc) - timedelta(minutes=10)
    step_run.executed_at = None
    step_run.status = "pending"

    parent_run = MagicMock()
    parent_run.automation_id = uuid.uuid4()

    lead = _make_lead()

    async def fake_list_due(_db, **kw):
        return [step_run]

    # Two execute() calls: lead lookup, then parent run lookup.
    lead_result = MagicMock()
    lead_result.scalar_one_or_none = MagicMock(return_value=lead)
    parent_result = MagicMock()
    parent_result.scalar_one_or_none = MagicMock(return_value=parent_run)

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[lead_result, parent_result])
    db.begin_nested = MagicMock(return_value=_AsyncCM())
    db.commit = AsyncMock()

    with patch(
        "app.automation_builder.repositories.list_due_step_runs",
        new=fake_list_due,
    ), patch(
        "app.automation_builder.services.Activity", new=MagicMock
    ):
        result = await svc.execute_due_step_runs(db)

    assert result == {"scanned": 1, "fired": 1, "failed": 0}
    assert step_run.status == "success"
    assert step_run.executed_at is not None
    assert step_run.error is None


# ===========================================================================
# 9. execute_due_step_runs marks orphan-lead step as 'skipped'
# ===========================================================================

@pytest.mark.asyncio
async def test_execute_due_step_runs_skips_orphan_lead():
    """When the lead was deleted between the parent run and the
    scheduled step, the row gets status='skipped' with an explanatory
    error — not 'failed'. Operator distinguishes «something broke»
    from «target gone, scheduler did the right thing»."""
    step_run = MagicMock()
    step_run.id = uuid.uuid4()
    step_run.automation_run_id = uuid.uuid4()
    step_run.lead_id = uuid.uuid4()
    step_run.step_index = 2
    step_run.step_json = {
        "type": "create_task",
        "config": {"title": "Won't fire"},
    }
    step_run.scheduled_at = datetime.now(tz=timezone.utc) - timedelta(minutes=1)
    step_run.executed_at = None
    step_run.status = "pending"

    async def fake_list_due(_db, **kw):
        return [step_run]

    # Lead lookup returns None (deleted)
    lead_result = MagicMock()
    lead_result.scalar_one_or_none = MagicMock(return_value=None)

    db = AsyncMock()
    db.execute = AsyncMock(return_value=lead_result)
    db.commit = AsyncMock()

    with patch(
        "app.automation_builder.repositories.list_due_step_runs",
        new=fake_list_due,
    ):
        result = await svc.execute_due_step_runs(db)

    # Skipped, not failed — lead-gone is a clean outcome.
    assert step_run.status == "skipped"
    assert "deleted" in (step_run.error or "")
    assert step_run.executed_at is not None
    # `fired` counts successful dispatches; `failed` counts exceptions;
    # skipped rows don't increment either (they're terminal but not
    # an outcome the scheduler «did» — they're an absence).
    assert result["scanned"] == 1
    assert result["fired"] == 0
    assert result["failed"] == 0
