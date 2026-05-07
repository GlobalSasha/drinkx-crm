"""Unit tests for daily_plan.priority_scorer — Sprint 1.4.

Pure function tests, no DB required.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import ModuleType
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Minimal sqlalchemy stub — mirrored from test_enrichment_orchestrator.py
# ---------------------------------------------------------------------------

def _stub_sqlalchemy():
    if "sqlalchemy" in sys.modules:
        return

    def _noop(*a, **kw):
        return None

    class _Callable:
        _instance = None
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

from app.daily_plan.priority_scorer import (  # noqa: E402
    DUE_SOON_WINDOW,
    P_ARCHIVED_OR_TERMINAL,
    P_NOT_ASSIGNED,
    W_DUE_SOON,
    W_FIT_MULTIPLIER,
    W_OVERDUE,
    W_PRIORITY_A,
    W_PRIORITY_B,
    W_PRIORITY_C,
    W_ROTTING,
    score_lead,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NOW = datetime(2026, 5, 7, 9, 0, 0, tzinfo=timezone.utc)


def _lead(
    *,
    priority: str | None = None,
    next_action_at: datetime | None = None,
    is_rotting_stage: bool = False,
    is_rotting_next_step: bool = False,
    fit_score: float | None = None,
    archived_at=None,
    won_at=None,
    lost_at=None,
    assignment_status: str = "assigned",
) -> MagicMock:
    lead = MagicMock()
    lead.priority = priority
    lead.next_action_at = next_action_at
    lead.is_rotting_stage = is_rotting_stage
    lead.is_rotting_next_step = is_rotting_next_step
    lead.fit_score = fit_score
    lead.archived_at = archived_at
    lead.won_at = won_at
    lead.lost_at = lost_at
    lead.assignment_status = assignment_status
    return lead


def _stage(probability: int = 50) -> MagicMock:
    stage = MagicMock()
    stage.probability = probability
    return stage


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_base_is_stage_probability():
    lead = _lead()
    stage = _stage(probability=40)
    result = score_lead(lead, stage, NOW)
    assert result == Decimal("40")


def test_overdue_adds_25():
    overdue_time = NOW - timedelta(hours=1)
    lead = _lead(next_action_at=overdue_time)
    result = score_lead(lead, _stage(probability=0), NOW)
    assert result == W_OVERDUE


def test_due_soon_adds_15_within_24h():
    due_soon = NOW + timedelta(hours=12)  # within 24h window
    lead = _lead(next_action_at=due_soon)
    result = score_lead(lead, _stage(probability=0), NOW)
    assert result == W_DUE_SOON


def test_due_soon_not_triggered_beyond_24h():
    far_future = NOW + timedelta(hours=25)
    lead = _lead(next_action_at=far_future)
    result = score_lead(lead, _stage(probability=0), NOW)
    assert result == Decimal("0")


def test_priority_a_b_c_weights():
    base_stage = _stage(probability=0)
    assert score_lead(_lead(priority="A"), base_stage, NOW) == W_PRIORITY_A
    assert score_lead(_lead(priority="B"), base_stage, NOW) == W_PRIORITY_B
    assert score_lead(_lead(priority="C"), base_stage, NOW) == W_PRIORITY_C
    assert score_lead(_lead(priority="D"), base_stage, NOW) == Decimal("0")
    assert score_lead(_lead(priority=None), base_stage, NOW) == Decimal("0")


def test_rotting_stage_adds_20():
    lead = _lead(is_rotting_stage=True)
    result = score_lead(lead, _stage(probability=0), NOW)
    assert result == W_ROTTING


def test_rotting_next_step_adds_20():
    lead = _lead(is_rotting_next_step=True)
    result = score_lead(lead, _stage(probability=0), NOW)
    assert result == W_ROTTING


def test_both_rotting_flags_count_once_not_twice():
    """When both rotting flags are True, W_ROTTING is added only once."""
    lead = _lead(is_rotting_stage=True, is_rotting_next_step=True)
    result = score_lead(lead, _stage(probability=0), NOW)
    assert result == W_ROTTING  # not 40


def test_fit_score_contributes_linearly():
    lead = _lead(fit_score=7.5)
    result = score_lead(lead, _stage(probability=0), NOW)
    assert result == Decimal("7.5") * W_FIT_MULTIPLIER


def test_fit_score_none_contributes_zero():
    lead = _lead(fit_score=None)
    result = score_lead(lead, _stage(probability=0), NOW)
    assert result == Decimal("0")


def test_archived_or_won_or_lost_subtracts_50():
    from datetime import datetime, timezone as tz
    ts = datetime(2026, 1, 1, tzinfo=tz.utc)
    base_stage = _stage(probability=0)

    assert score_lead(_lead(archived_at=ts), base_stage, NOW) == P_ARCHIVED_OR_TERMINAL
    assert score_lead(_lead(won_at=ts), base_stage, NOW) == P_ARCHIVED_OR_TERMINAL
    assert score_lead(_lead(lost_at=ts), base_stage, NOW) == P_ARCHIVED_OR_TERMINAL


def test_unassigned_leads_get_severe_penalty():
    lead = _lead(assignment_status="pool")
    result = score_lead(lead, _stage(probability=0), NOW)
    assert result == P_NOT_ASSIGNED


def test_no_stage_means_zero_baseline():
    lead = _lead()
    result = score_lead(lead, None, NOW)
    assert result == Decimal("0")


def test_combination_realistic_lead():
    """Hot lead (overdue, priority A, fit_score=8) scores higher than cold lead."""
    hot_lead = _lead(
        priority="A",
        next_action_at=NOW - timedelta(hours=2),  # overdue
        fit_score=8.0,
        is_rotting_stage=True,
    )
    hot_stage = _stage(probability=60)
    hot_score = score_lead(hot_lead, hot_stage, NOW)

    cold_lead = _lead(
        priority="D",
        next_action_at=None,
        fit_score=2.0,
        is_rotting_stage=False,
    )
    cold_stage = _stage(probability=5)
    cold_score = score_lead(cold_lead, cold_stage, NOW)

    assert hot_score > cold_score

    # Sanity check the hot score:
    # 60 (prob) + 25 (overdue) + 10 (prio A) + 20 (rotting) + 8 (fit) = 123
    assert hot_score == Decimal("123")
