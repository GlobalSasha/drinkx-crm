"""Tests for plan 016 — visible failure for tg/sms `send_template` steps.

Mock-only — same sqlalchemy stub pattern as test_automation_multistep.py /
test_automation_builder_service.py. Covers:

  1. A tg `send_template` step 0 is recorded `skipped` (not `success`),
     with a `channel_not_implemented:tg` reason, via `evaluate_trigger`.
  2. The rest of the chain still gets scheduled — a skip does not halt
     the chain the way a real failure does.
  3. The parent run row stays `success` (a skip is not a failure).
  4. An `email` `send_template` step 0 still records `success`.
  5. `create_automation` rejects a `send_template` action referencing a
     tg/sms template at save time (`UnsupportedTemplateChannel`).
  6. `create_automation` still accepts a `send_template` action
     referencing an `email` template.
  7. `execute_due_step_runs` records a scheduler-fired tg step as
     `skipped` (terminal, no retry) instead of `failed`.
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# sqlalchemy stub — same as test_automation_multistep.py / test_automation_
# reliability.py.
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
    a.action_type = kw.get("action_type", "send_template")
    a.action_config_json = kw.get(
        "action_config_json", {"template_id": str(uuid.uuid4())}
    )
    a.steps_json = kw.get("steps_json", None)
    a.is_active = True
    return a


def _make_template(**kw):
    t = MagicMock()
    t.id = kw.get("id", uuid.uuid4())
    t.workspace_id = kw.get("workspace_id", WS)
    t.channel = kw.get("channel", "tg")
    t.name = kw.get("name", "Followup")
    t.text = kw.get("text", "Hi {{lead.company_name}}")
    return t


def _template_result(template):
    """A `db.execute(select(MessageTemplate)...)` result stub whose
    `.scalar_one_or_none()` returns the given template (or None)."""
    res = MagicMock()
    res.scalar_one_or_none = MagicMock(return_value=template)
    return res


class _AsyncCM:
    async def __aenter__(self): return self
    async def __aexit__(self, *_): return False


# ===========================================================================
# 1-3. evaluate_trigger: tg send_template step 0 is `skipped`, chain
# continues, parent run stays `success`.
# ===========================================================================

@pytest.mark.asyncio
async def test_evaluate_trigger_tg_template_step_is_skipped_not_success():
    """A `send_template` step 0 on a tg template must not read as a
    false-positive `success` — it's recorded `skipped` with an explicit
    `channel_not_implemented:tg` reason, and the rest of the chain
    (step 2) still gets scheduled."""
    template = _make_template(channel="tg")
    auto = _make_automation(
        steps_json=[
            {
                "type": "send_template",
                "config": {"template_id": str(template.id)},
            },
            {"type": "delay_hours", "config": {"hours": 1}},
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
    db.execute = AsyncMock(return_value=_template_result(template))
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

    # Parent run row is NOT failed — a skip is honest, not a failure.
    assert len(runs) == 1
    assert runs[0]["status"] == "success"

    # Step 0: skipped, with the reason surfaced as the step error.
    sr0 = next(r for r in step_rows if r["step_index"] == 0)
    assert sr0["status"] == "skipped"
    assert sr0["error"] == "channel_not_implemented:tg"
    assert sr0["executed_at"] is not None

    # Chain continues past the skip — step 2 still scheduled.
    sr2 = next((r for r in step_rows if r["step_index"] == 2), None)
    assert sr2 is not None
    assert sr2["status"] == "pending"


@pytest.mark.asyncio
async def test_evaluate_trigger_sms_template_step_is_skipped():
    """Same as the tg case, for the sms channel — the reason string
    reflects the actual channel."""
    template = _make_template(channel="sms")
    auto = _make_automation(
        action_type="send_template",
        action_config_json={"template_id": str(template.id)},
        steps_json=None,
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
    db.execute = AsyncMock(return_value=_template_result(template))
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

    assert runs[0]["status"] == "success"
    assert step_rows[0]["status"] == "skipped"
    assert step_rows[0]["error"] == "channel_not_implemented:sms"


# ===========================================================================
# 4. An email send_template step still records `success`.
# ===========================================================================

@pytest.mark.asyncio
async def test_evaluate_trigger_email_template_step_still_success():
    """The email path is untouched by plan 016 — it still records
    `success` (this is the honest state; SMTP dispatch happens
    post-commit as already documented on `_send_template_action`)."""
    template = _make_template(channel="email")
    auto = _make_automation(
        action_type="send_template",
        action_config_json={"template_id": str(template.id)},
        steps_json=None,
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
    db.execute = AsyncMock(return_value=_template_result(template))
    db.flush = AsyncMock()
    lead = _make_lead(email="buyer@example.com")

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

    assert runs[0]["status"] == "success"
    assert step_rows[0]["status"] == "success"
    assert step_rows[0]["error"] is None


# ===========================================================================
# 5. create_automation rejects a send_template action on a tg/sms template.
# ===========================================================================

@pytest.mark.asyncio
async def test_create_rejects_send_template_on_tg_template():
    """Step 2 (plan 016) — the misconfiguration is caught at authoring
    time, before it can silently no-op at fire time."""
    template = _make_template(channel="tg")

    db = AsyncMock()
    db.execute = AsyncMock(return_value=_template_result(template))

    with pytest.raises(svc.UnsupportedTemplateChannel):
        await svc.create_automation(
            db,
            workspace_id=WS,
            created_by=None,
            name="tg followup",
            trigger="stage_change",
            trigger_config_json=None,
            condition_json=None,
            action_type="send_template",
            action_config_json={"template_id": str(template.id)},
        )


# ===========================================================================
# 6. create_automation still accepts a send_template action on an email
# template.
# ===========================================================================

@pytest.mark.asyncio
async def test_create_accepts_send_template_on_email_template():
    template = _make_template(channel="email")

    db = AsyncMock()
    db.execute = AsyncMock(return_value=_template_result(template))

    async def fake_create(_db, **kw):
        out = MagicMock()
        for k, v in kw.items():
            setattr(out, k, v)
        out.id = uuid.uuid4()
        return out

    with patch(
        "app.automation_builder.repositories.create", new=fake_create
    ):
        result = await svc.create_automation(
            db,
            workspace_id=WS,
            created_by=None,
            name="email followup",
            trigger="stage_change",
            trigger_config_json=None,
            condition_json=None,
            action_type="send_template",
            action_config_json={"template_id": str(template.id)},
        )

    assert result.action_type == "send_template"


# ===========================================================================
# 7. execute_due_step_runs records a tg send_template step as `skipped`,
# not `failed` — terminal, no retry.
# ===========================================================================

@pytest.mark.asyncio
async def test_execute_due_step_runs_marks_tg_template_step_skipped():
    template = _make_template(channel="tg")
    step_run = MagicMock()
    step_run.id = uuid.uuid4()
    step_run.automation_run_id = uuid.uuid4()
    step_run.lead_id = LEAD_ID
    step_run.step_index = 1
    step_run.step_json = {
        "type": "send_template",
        "config": {"template_id": str(template.id)},
    }
    step_run.scheduled_at = datetime.now(tz=timezone.utc) - timedelta(minutes=10)
    step_run.executed_at = None
    step_run.status = "pending"
    step_run.error = None
    step_run.attempt_count = 0

    parent_run = MagicMock()
    parent_run.automation_id = uuid.uuid4()
    lead = _make_lead()

    async def fake_list_due(_db, **kw):
        return [step_run]

    lead_result = MagicMock()
    lead_result.scalar_one_or_none = MagicMock(return_value=lead)
    parent_result = MagicMock()
    parent_result.scalar_one_or_none = MagicMock(return_value=parent_run)
    template_result = _template_result(template)

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[lead_result, parent_result, template_result]
    )
    db.begin_nested = MagicMock(return_value=_AsyncCM())
    db.commit = AsyncMock()

    with patch(
        "app.automation_builder.repositories.list_due_step_runs",
        new=fake_list_due,
    ):
        result = await svc.execute_due_step_runs(db)

    assert step_run.status == "skipped"
    assert step_run.error == "channel_not_implemented:tg"
    assert step_run.executed_at is not None
    assert result["fired"] == 0
    assert result["failed"] == 0
    assert result["skipped"] == 1
