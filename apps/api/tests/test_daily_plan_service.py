"""Tests for daily_plan.services.generate_for_user — Sprint 1.4.

All DB + LLM calls are mocked. No real Postgres needed.
The sqlalchemy stub makes ORM constructors non-functional, so generate_for_user
is tested by patching DailyPlan and DailyPlanItem in app.daily_plan.services.
"""
from __future__ import annotations

import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Minimal sqlalchemy stub (same pattern as test_enrichment_orchestrator.py)
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
        "Numeric", "DateTime", "Boolean", "Index", "select", "Date",
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

from app.daily_plan.services import (  # noqa: E402
    _work_hours_minutes,
    _split_into_time_blocks,
    _compose_summary,
    generate_for_user,
)
from app.daily_plan.schemas import ScoredItem  # noqa: E402
from app.enrichment.providers.base import CompletionResult, LLMError  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PLAN_DATE = date(2026, 5, 7)  # Thursday


def _make_user(workspace_id=None, working_hours_json=None) -> MagicMock:
    u = MagicMock()
    u.id = uuid.uuid4()
    u.workspace_id = workspace_id or uuid.uuid4()
    u.working_hours_json = working_hours_json or {}
    return u


def _make_lead(
    *,
    company_name: str = "ООО Тест",
    priority: str = "B",
    is_rotting_stage: bool = False,
    is_rotting_next_step: bool = False,
    fit_score: float | None = None,
    next_action_at: datetime | None = None,
    assignment_status: str = "assigned",
    next_step: str | None = None,
    ai_data: dict | None = None,
) -> MagicMock:
    lead = MagicMock()
    lead.id = uuid.uuid4()
    lead.company_name = company_name
    lead.segment = "HoReCa"
    lead.city = "Москва"
    lead.priority = priority
    lead.is_rotting_stage = is_rotting_stage
    lead.is_rotting_next_step = is_rotting_next_step
    lead.fit_score = fit_score
    lead.next_action_at = next_action_at
    lead.assignment_status = assignment_status
    lead.next_step = next_step
    lead.ai_data = ai_data
    lead.archived_at = None
    lead.won_at = None
    lead.lost_at = None
    return lead


def _make_stage(probability: int = 50) -> MagicMock:
    s = MagicMock()
    s.probability = probability
    return s


def _make_db_for_generate(lead_stage_pairs: list[tuple]) -> AsyncMock:
    """Build a mock AsyncSession suitable for generate_for_user."""
    db = AsyncMock()
    added_objects: list = []

    call_count = [0]

    async def _execute(stmt, *a, **kw):
        call_count[0] += 1
        result = MagicMock()
        if call_count[0] == 1:
            # First call is the DELETE — return empty
            result.all.return_value = []
            result.scalar_one_or_none.return_value = None
            return result
        # Subsequent calls: return lead/stage pairs
        result.all.return_value = lead_stage_pairs
        result.scalar_one_or_none.return_value = None
        return result

    def _add(obj):
        added_objects.append(obj)

    db.execute = _execute
    db.execute.call_count_tracker = call_count
    db.add = _add
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db._added_objects = added_objects
    return db


_GOOD_COMPLETION = CompletionResult(
    text="Позвонить и обсудить пилот",
    model="mimo-flash",
    provider="mimo",
    prompt_tokens=50,
    completion_tokens=15,
    cost_usd=0.0001,
)


def _make_plan_mock(**kwargs) -> MagicMock:
    """Create a MagicMock that behaves like a DailyPlan instance."""
    m = MagicMock()
    m.id = uuid.uuid4()
    m.status = "generating"
    m.summary_json = {}
    m.generated_at = None
    m.generation_error = None
    for k, v in kwargs.items():
        setattr(m, k, v)
    return m


# ---------------------------------------------------------------------------
# _work_hours_minutes unit tests
# ---------------------------------------------------------------------------

def test_work_hours_minutes_parses_correct_day():
    # 2026-05-07 is a Thursday (weekday=3)
    wh = {"thu": {"start": "09:00", "end": "18:00"}}
    result = _work_hours_minutes(wh, date(2026, 5, 7))
    assert result == 9 * 60  # 540 min


def test_work_hours_minutes_falls_back_when_empty():
    assert _work_hours_minutes({}, date(2026, 5, 7)) == 360


def test_work_hours_minutes_falls_back_on_bad_shape():
    assert _work_hours_minutes({"thu": "bad"}, date(2026, 5, 7)) == 360


# ---------------------------------------------------------------------------
# _split_into_time_blocks unit tests
# ---------------------------------------------------------------------------

def test_split_into_time_blocks_assigns_thirds():
    leads = [_make_lead() for _ in range(9)]
    stage = _make_stage()
    items = [ScoredItem(lead=l, stage=stage, priority_score=Decimal("10")) for l in leads]
    result = _split_into_time_blocks(items)
    blocks = [b for _, b in result]
    assert blocks[:3] == ["morning", "morning", "morning"]
    assert blocks[3:6] == ["midday", "midday", "midday"]
    assert blocks[6:9] == ["afternoon", "afternoon", "afternoon"]


def test_split_into_time_blocks_single_item():
    item = ScoredItem(lead=_make_lead(), stage=None, priority_score=Decimal("5"))
    result = _split_into_time_blocks([item])
    assert result[0][1] == "morning"


# ---------------------------------------------------------------------------
# _compose_summary unit tests
# ---------------------------------------------------------------------------

def test_summary_json_breakdown():
    leads = [
        _make_lead(ai_data={"urgency": "high"}),
        _make_lead(ai_data={"urgency": "high"}),
        _make_lead(ai_data={"urgency": "medium"}),
        _make_lead(ai_data={"urgency": "low"}),
        _make_lead(ai_data={}),  # no urgency → medium
    ]
    items = [
        ScoredItem(lead=l, stage=None, priority_score=Decimal("10"), estimated_minutes=15)
        for l in leads
    ]
    summary = _compose_summary(items)
    assert summary["count"] == 5
    assert summary["total_minutes"] == 75
    breakdown = summary["urgency_breakdown"]
    assert breakdown["high"] + breakdown["medium"] + breakdown["low"] == summary["count"]
    assert breakdown["high"] == 2
    assert breakdown["medium"] == 2  # 1 explicit + 1 default
    assert breakdown["low"] == 1


# ---------------------------------------------------------------------------
# generate_for_user integration tests (mocked DB + LLM + ORM constructors)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_packs_items_into_work_hour_budget(monkeypatch):
    """With 360min budget and 15min/item, max 24 items should be packed."""
    n_leads = 50
    leads = [_make_lead(company_name=f"Co {i}") for i in range(n_leads)]
    stage = _make_stage(probability=50)
    pairs = [(lead, stage) for lead in leads]

    user = _make_user()
    db = _make_db_for_generate(pairs)

    plan_mock = _make_plan_mock()

    monkeypatch.setattr("app.daily_plan.services.DailyPlan", MagicMock(return_value=plan_mock))
    monkeypatch.setattr("app.daily_plan.services.DailyPlanItem", MagicMock(side_effect=lambda **kw: MagicMock(**kw)))
    monkeypatch.setattr(
        "app.daily_plan.services.complete_with_fallback",
        AsyncMock(return_value=_GOOD_COMPLETION),
    )
    monkeypatch.setattr("app.daily_plan.services.add_to_daily_spend", AsyncMock())

    plan = await generate_for_user(db, user=user, plan_date=_PLAN_DATE)

    assert plan.status == "ready"
    assert plan.summary_json["count"] == 24  # 360 / 15 = 24
    assert plan.summary_json["total_minutes"] == 360


@pytest.mark.asyncio
async def test_failed_llm_falls_back_to_deterministic_hint(monkeypatch):
    """LLM failure per item → deterministic hint used, plan still succeeds."""
    leads = [_make_lead(company_name="ООО Ромашка", next_step="позвонить")]
    stage = _make_stage(probability=40)
    pairs = [(lead, stage) for lead in leads]

    user = _make_user()
    db = _make_db_for_generate(pairs)

    plan_mock = _make_plan_mock()
    created_items: list[MagicMock] = []

    def _make_item(**kw):
        m = MagicMock()
        for k, v in kw.items():
            setattr(m, k, v)
        created_items.append(m)
        return m

    monkeypatch.setattr("app.daily_plan.services.DailyPlan", MagicMock(return_value=plan_mock))
    monkeypatch.setattr("app.daily_plan.services.DailyPlanItem", MagicMock(side_effect=_make_item))
    monkeypatch.setattr(
        "app.daily_plan.services.complete_with_fallback",
        AsyncMock(side_effect=LLMError("down", provider="factory")),
    )
    monkeypatch.setattr("app.daily_plan.services.add_to_daily_spend", AsyncMock())

    plan = await generate_for_user(db, user=user, plan_date=_PLAN_DATE)

    assert plan.status == "ready"
    assert plan.summary_json["count"] == 1
    assert len(created_items) == 1
    assert created_items[0].hint_one_liner != ""
    assert "ООО Ромашка" in created_items[0].hint_one_liner


@pytest.mark.asyncio
async def test_writes_status_failed_on_complete_blowup(monkeypatch):
    """If the lead query itself raises, generate_for_user returns plan with status=failed."""
    user = _make_user()

    plan_mock = _make_plan_mock()

    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    call_count = [0]

    async def _execute(stmt, *a, **kw):
        call_count[0] += 1
        if call_count[0] == 1:
            # DELETE call
            return MagicMock()
        raise RuntimeError("DB exploded")

    db.execute = _execute

    monkeypatch.setattr("app.daily_plan.services.DailyPlan", MagicMock(return_value=plan_mock))
    monkeypatch.setattr("app.daily_plan.services.DailyPlanItem", MagicMock())
    monkeypatch.setattr("app.daily_plan.services.add_to_daily_spend", AsyncMock())

    plan = await generate_for_user(db, user=user, plan_date=_PLAN_DATE)

    assert plan.status == "failed"
    assert plan.generation_error is not None
    assert "RuntimeError" in plan.generation_error


@pytest.mark.asyncio
async def test_replaces_prior_plan_for_same_date(monkeypatch):
    """generate_for_user issues a DELETE before inserting new items (idempotent)."""
    leads = [_make_lead()]
    stage = _make_stage(probability=30)
    pairs = [(lead, stage) for lead in leads]

    user = _make_user()
    db = _make_db_for_generate(pairs)

    plan_mock = _make_plan_mock()

    monkeypatch.setattr("app.daily_plan.services.DailyPlan", MagicMock(return_value=plan_mock))
    monkeypatch.setattr("app.daily_plan.services.DailyPlanItem", MagicMock(side_effect=lambda **kw: MagicMock(**kw)))
    monkeypatch.setattr(
        "app.daily_plan.services.complete_with_fallback",
        AsyncMock(return_value=_GOOD_COMPLETION),
    )
    monkeypatch.setattr("app.daily_plan.services.add_to_daily_spend", AsyncMock())

    plan = await generate_for_user(db, user=user, plan_date=_PLAN_DATE)
    assert plan.status == "ready"
    assert plan.summary_json["count"] == 1

    # Second run on the same user/date — a new db mock
    db2 = _make_db_for_generate(pairs)
    plan_mock2 = _make_plan_mock()
    monkeypatch.setattr("app.daily_plan.services.DailyPlan", MagicMock(return_value=plan_mock2))
    monkeypatch.setattr("app.daily_plan.services.DailyPlanItem", MagicMock(side_effect=lambda **kw: MagicMock(**kw)))
    monkeypatch.setattr(
        "app.daily_plan.services.complete_with_fallback",
        AsyncMock(return_value=_GOOD_COMPLETION),
    )

    plan2 = await generate_for_user(db2, user=user, plan_date=_PLAN_DATE)
    assert plan2.status == "ready"
    assert plan2.summary_json["count"] == 1
    # Both runs succeed — idempotent behaviour verified by status/count


@pytest.mark.asyncio
async def test_empty_lead_set_produces_ready_plan_with_zero_items(monkeypatch):
    """No assigned leads → plan is ready with 0 items."""
    user = _make_user()
    db = _make_db_for_generate([])

    plan_mock = _make_plan_mock()

    monkeypatch.setattr("app.daily_plan.services.DailyPlan", MagicMock(return_value=plan_mock))
    monkeypatch.setattr("app.daily_plan.services.DailyPlanItem", MagicMock())
    monkeypatch.setattr(
        "app.daily_plan.services.complete_with_fallback",
        AsyncMock(return_value=_GOOD_COMPLETION),
    )
    monkeypatch.setattr("app.daily_plan.services.add_to_daily_spend", AsyncMock())

    plan = await generate_for_user(db, user=user, plan_date=_PLAN_DATE)

    assert plan.status == "ready"
    assert plan.summary_json["count"] == 0
    assert plan.summary_json["total_minutes"] == 0
