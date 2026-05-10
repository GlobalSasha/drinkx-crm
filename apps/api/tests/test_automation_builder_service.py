"""Tests for app.automation_builder — Sprint 2.5 G1.

Mock-only — same sqlalchemy stub pattern as test_users_service.py.
12 tests covering CRUD validation, condition evaluator, render
substitution, trigger fan-out (success / skip / failure isolation),
and the action handlers' arg validation.
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
from app.automation_builder.condition import evaluate as evaluate_condition  # noqa: E402
from app.automation_builder.render import render_template_text  # noqa: E402

WS = uuid.uuid4()
ADMIN = uuid.uuid4()
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
    lead.source = kw.get("source", None)
    lead.assignment_status = kw.get("assignment_status", "pool")
    lead.company_name = kw.get("company_name", "Acme Corp")
    lead.city = kw.get("city", "Moscow")
    lead.email = kw.get("email", None)
    lead.phone = kw.get("phone", None)
    lead.website = kw.get("website", None)
    lead.segment = kw.get("segment", None)
    lead.next_step = kw.get("next_step", None)
    lead.blocker = kw.get("blocker", None)
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
    a.is_active = kw.get("is_active", True)
    return a


class _AsyncCM:
    """Sprint 2.6 G1 stability fix #2: `evaluate_trigger` wraps each
    per-automation action in `db.begin_nested()`. AsyncMock doesn't
    auto-produce an async context manager from a method call, so
    tests that exercise the SAVEPOINT path attach `db.begin_nested =
    MagicMock(return_value=_AsyncCM())`."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        # Returning False (or None) propagates the exception, matching
        # SQLAlchemy's begin_nested behaviour when an exception
        # bubbles out of the `with` block (savepoint rolls back, then
        # the exception re-raises to the outer try/except).
        return False


# ===========================================================================
# 1. create rejects unknown trigger
# ===========================================================================

@pytest.mark.asyncio
async def test_create_rejects_unknown_trigger():
    """Pydantic Literal catches this at the API boundary in real use,
    but the service is the last line of defense if a buggy caller
    bypasses the schema."""
    db = AsyncMock()
    with pytest.raises(svc.InvalidTrigger):
        await svc.create_automation(
            db,
            workspace_id=WS,
            created_by=ADMIN,
            name="x",
            trigger="bogus",
            trigger_config_json=None,
            condition_json=None,
            action_type="create_task",
            action_config_json={"title": "t"},
        )


# ===========================================================================
# 2. create rejects send_template without template_id
# ===========================================================================

@pytest.mark.asyncio
async def test_create_rejects_send_template_without_template_id():
    """Action config validation prevents a half-configured automation
    from sitting in the DB and silently failing every fire."""
    db = AsyncMock()
    with pytest.raises(svc.InvalidActionConfig):
        await svc.create_automation(
            db,
            workspace_id=WS,
            created_by=ADMIN,
            name="x",
            trigger="stage_change",
            trigger_config_json=None,
            condition_json=None,
            action_type="send_template",
            action_config_json={},  # missing template_id
        )


# ===========================================================================
# 3. create happy path
# ===========================================================================

@pytest.mark.asyncio
async def test_create_happy_path():
    """Service trims name + delegates to repo. created_by flows
    through for the audit trail."""
    db = AsyncMock()
    create_calls: list[dict] = []

    async def fake_create(_db, **kw):
        create_calls.append(kw)
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
            created_by=ADMIN,
            name="  Welcome flow  ",
            trigger="form_submission",
            trigger_config_json={"form_id": str(uuid.uuid4())},
            condition_json=None,
            action_type="create_task",
            action_config_json={"title": "Reach out", "due_in_hours": 12},
        )

    assert len(create_calls) == 1
    assert create_calls[0]["name"] == "Welcome flow"
    assert create_calls[0]["created_by"] == ADMIN
    assert result.action_type == "create_task"


# ===========================================================================
# 4. condition evaluator — simple AND
# ===========================================================================

def test_condition_all_eq_and_gte():
    """all-block requires every clause to pass. Standard AND semantics."""
    lead = _make_lead(priority="A", score=75)
    cond = {
        "all": [
            {"field": "priority", "op": "eq", "value": "A"},
            {"field": "score", "op": "gte", "value": 60},
        ]
    }
    assert evaluate_condition(cond, lead) is True

    lead_b = _make_lead(priority="B", score=75)
    assert evaluate_condition(cond, lead_b) is False


# ===========================================================================
# 5. condition evaluator — null condition fires
# ===========================================================================

def test_condition_null_always_fires():
    """No condition = «always fire». An admin who doesn't set a
    condition wants the automation to run every time the trigger
    fires."""
    lead = _make_lead()
    assert evaluate_condition(None, lead) is True
    assert evaluate_condition({}, lead) is True


# ===========================================================================
# 6. condition evaluator — unknown field defends with False
# ===========================================================================

def test_condition_unknown_field_returns_false():
    """Field not in ALLOWED_FIELDS → False with a log warning. Stale
    UI bundles can't crash the trigger fan-out — they just don't
    fire that automation."""
    lead = _make_lead()
    cond = {"all": [{"field": "deleted_field", "op": "eq", "value": "x"}]}
    assert evaluate_condition(cond, lead) is False


# ===========================================================================
# 7. render substitutes lead fields
# ===========================================================================

def test_render_substitutes_lead_fields():
    """`{{lead.company_name}}` becomes the actual company name. Other
    placeholders stay verbatim if not in the allowlist."""
    lead = _make_lead(company_name="Acme Corp", city="Moscow")
    out = render_template_text(
        "Hi {{lead.company_name}} from {{lead.city}}!", lead
    )
    assert out == "Hi Acme Corp from Moscow!"


# ===========================================================================
# 8. render emits [unknown:foo] for non-allowlisted fields
# ===========================================================================

def test_render_unknown_field_marker():
    """Unknown fields produce `[unknown:foo]` in the output (not the
    literal `{{lead.foo}}`) so the audit trail shows the operator
    typed something wrong, plus a worker log warning fires."""
    lead = _make_lead()
    out = render_template_text(
        "Hi {{lead.foo}} from {{lead.city}}!", lead
    )
    assert "[unknown:foo]" in out
    assert "{{lead.foo}}" not in out
    assert "Moscow" in out


# ===========================================================================
# 9. evaluate_trigger filters by per-trigger config (stage_change)
# ===========================================================================

@pytest.mark.asyncio
async def test_evaluate_trigger_stage_change_to_stage_filter():
    """When trigger_config_json has `to_stage_id`, only fire if the
    incoming payload's `to_stage_id` matches. Non-matching automations
    are silently skipped (no run row, since they don't even consider
    the condition)."""
    target_stage = uuid.uuid4()
    other_stage = uuid.uuid4()

    matching = _make_automation(
        trigger="stage_change",
        trigger_config_json={"to_stage_id": str(target_stage)},
        action_type="create_task",
        action_config_json={"title": "Hit"},
    )
    non_matching = _make_automation(
        trigger="stage_change",
        trigger_config_json={"to_stage_id": str(other_stage)},
        action_type="create_task",
        action_config_json={"title": "Miss"},
    )

    runs: list[dict] = []

    async def fake_list_active(_db, **kw):
        return [matching, non_matching]

    async def fake_create_run(_db, **kw):
        runs.append(kw)
        return MagicMock()

    async def fake_create_step_run(_db, **kw):
        # Sprint 2.7 G2 — `evaluate_trigger` now also writes a step-0
        # audit row (and step 1+ for multi-step). Tests that don't
        # care about per-step audit just MagicMock past it.
        return MagicMock()

    db = AsyncMock()
    db.begin_nested = MagicMock(return_value=_AsyncCM())
    lead = _make_lead()

    # `_create_task_action` instantiates an Activity ORM row via
    # `db.add(Activity(...))`. Under the sqlalchemy stub the real
    # Activity class doesn't accept kwargs, so patch it to a flexible
    # MagicMock for the duration of the test. The test cares about
    # the run row, not the Activity row.
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
            payload={"to_stage_id": str(target_stage)},
        )

    # Only the matching automation logged a run — non-matching was
    # filtered out before condition evaluation.
    assert len(runs) == 1
    assert runs[0]["status"] == "success"
    assert runs[0]["automation_id"] == matching.id


# ===========================================================================
# 10. evaluate_trigger logs skipped when condition fails
# ===========================================================================

@pytest.mark.asyncio
async def test_evaluate_trigger_logs_skipped_on_condition_fail():
    """Condition not met → status=skipped row with error='condition_not_met'.
    Admin sees in the run history WHY their automation isn't firing."""
    auto = _make_automation(
        condition_json={
            "all": [{"field": "priority", "op": "eq", "value": "A"}]
        },
    )

    runs: list[dict] = []

    async def fake_list_active(_db, **kw):
        return [auto]

    async def fake_create_run(_db, **kw):
        runs.append(kw)
        return MagicMock()

    db = AsyncMock()
    lead = _make_lead(priority="C")  # condition wants A

    with patch(
        "app.automation_builder.repositories.list_active_for_trigger",
        new=fake_list_active,
    ), patch(
        "app.automation_builder.repositories.create_run",
        new=fake_create_run,
    ):
        await svc.evaluate_trigger(
            db,
            workspace_id=WS,
            trigger="stage_change",
            lead=lead,
            payload={},
        )

    assert len(runs) == 1
    assert runs[0]["status"] == "skipped"
    assert runs[0]["error"] == "condition_not_met"


# ===========================================================================
# 11. evaluate_trigger isolates failures per automation
# ===========================================================================

@pytest.mark.asyncio
async def test_evaluate_trigger_isolates_failures():
    """If one automation's action handler raises, the others still
    run. Failed run gets logged with the error truncated to 500 chars.
    Critical for keeping the parent stage_change/form-create/inbox
    transaction alive — one broken rule must not break the rest."""
    failing = _make_automation(
        action_type="move_stage",
        action_config_json={"target_stage_id": "not-a-uuid"},  # explodes in handler
    )
    passing = _make_automation(
        action_type="create_task",
        action_config_json={"title": "Ok"},
    )

    runs: list[dict] = []

    async def fake_list_active(_db, **kw):
        return [failing, passing]

    async def fake_create_run(_db, **kw):
        runs.append(kw)
        return MagicMock()

    async def fake_create_step_run(_db, **kw):
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

    assert len(runs) == 2
    statuses = {r["automation_id"]: r["status"] for r in runs}
    assert statuses[failing.id] == "failed"
    assert statuses[passing.id] == "success"


# ===========================================================================
# 12. update validates partial action_type/config combination
# ===========================================================================

@pytest.mark.asyncio
async def test_update_validates_partial_action_change():
    """If caller PATCHes action_type='send_template' without supplying
    a template_id alongside, validation fires using the resolved
    target config (passed-in OR existing). Surface as 400 ahead of
    leaving the row in an inconsistent half-changed state."""
    target = _make_automation(
        action_type="create_task",
        action_config_json={"title": "old"},
    )

    async def fake_get_by_id(_db, **kw):
        return target

    db = AsyncMock()

    with patch(
        "app.automation_builder.repositories.get_by_id",
        new=fake_get_by_id,
    ):
        with pytest.raises(svc.InvalidActionConfig):
            await svc.update_automation(
                db,
                automation_id=target.id,
                workspace_id=WS,
                action_type="send_template",
                # action_config_json NOT supplied → resolved config
                # falls back to {"title": "old"}, which is missing
                # template_id, validation kicks in.
            )
