"""Флаги застоя лида (app/leads/rotting.py) и их пересчёт при смене этапа."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

import app.main  # noqa: F401 -- registers SQLAlchemy mappers
from tests.conftest import POSTGRES_AVAILABLE

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires PostgreSQL")

NOW = datetime.now(timezone.utc)


# --- Pure unit: правило просроченного шага ---------------------------------

def test_rotting_next_step_rule():
    from app.leads.rotting import rotting_next_step

    past, future = NOW - timedelta(hours=1), NOW + timedelta(hours=1)
    assert rotting_next_step(in_work=True, next_action_at=past, now=NOW) is True
    assert rotting_next_step(in_work=True, next_action_at=future, now=NOW) is False
    assert rotting_next_step(in_work=True, next_action_at=None, now=NOW) is False
    assert rotting_next_step(in_work=False, next_action_at=past, now=NOW) is False


# --- Helpers ----------------------------------------------------------------

async def _stage(db, pipeline_id, *, rot_days=14, is_won=False, is_lost=False):
    from app.pipelines.models import Stage

    s = Stage(
        pipeline_id=pipeline_id,
        name=f"S-{uuid.uuid4().hex[:6]}",
        position=5,
        color="#aabbcc",
        rot_days=rot_days,
        is_won=is_won,
        is_lost=is_lost,
    )
    db.add(s)
    await db.flush()
    return s


async def _lead(
    db,
    workspace_id,
    stage,
    *,
    days_on_stage: int,
    assigned_to,
    pool=False,
    next_action_at=None,
    deal_amount=None,
    flags=False,
):
    """Лид, который вошёл на `stage` `days_on_stage` дней назад."""
    from app.leads.models import Lead, LeadStageHistory

    lead = Lead(
        workspace_id=workspace_id,
        company_name=f"Co {uuid.uuid4().hex[:6]}",
        assignment_status="pool" if pool else "assigned",
        assigned_to=None if pool else assigned_to,
        pipeline_id=stage.pipeline_id,
        stage_id=stage.id,
        next_action_at=next_action_at,
        deal_amount=deal_amount,
        is_rotting_stage=flags,
        is_rotting_next_step=flags,
    )
    db.add(lead)
    await db.flush()
    db.add(
        LeadStageHistory(
            lead_id=lead.id,
            stage_id=stage.id,
            entered_at=NOW - timedelta(days=days_on_stage, hours=1),
        )
    )
    await db.flush()
    return lead


async def _flags(db, lead) -> tuple[bool, bool]:
    row = (
        await db.execute(
            text("SELECT is_rotting_stage, is_rotting_next_step FROM leads WHERE id = :id"),
            {"id": str(lead.id)},
        )
    ).one()
    return row[0], row[1]


async def _recompute(db, workspace_id) -> int:
    from app.leads.rotting import recompute_workspace_rotting

    return await recompute_workspace_rotting(db, workspace_id)


# --- Правила пересчёта ------------------------------------------------------

@skip_no_pg
async def test_stage_rotting_over_rot_days(db, workspace, user, pipeline):
    p, stage = pipeline  # rot_days=14
    over = await _lead(db, workspace.id, stage, days_on_stage=20, assigned_to=user.id)
    under = await _lead(db, workspace.id, stage, days_on_stage=5, assigned_to=user.id)
    edge = await _lead(db, workspace.id, stage, days_on_stage=14, assigned_to=user.id)

    await _recompute(db, workspace.id)

    assert await _flags(db, over) == (True, False)
    assert await _flags(db, under) == (False, False)
    # Ровно rot_days — ещё не застрял (строго больше, как в прогнозе).
    assert await _flags(db, edge) == (False, False)


@skip_no_pg
async def test_rot_days_zero_never_rots(db, workspace, user, pipeline):
    p, _ = pipeline
    stage = await _stage(db, p.id, rot_days=0)
    lead = await _lead(db, workspace.id, stage, days_on_stage=300, assigned_to=user.id)

    await _recompute(db, workspace.id)

    assert await _flags(db, lead) == (False, False)


@skip_no_pg
async def test_closed_stages_always_false(db, workspace, user, pipeline):
    p, _ = pipeline
    won = await _stage(db, p.id, rot_days=1, is_won=True)
    lost = await _stage(db, p.id, rot_days=1, is_lost=True)
    past = NOW - timedelta(days=3)
    won_lead = await _lead(
        db, workspace.id, won, days_on_stage=100, assigned_to=user.id,
        next_action_at=past, flags=True,
    )
    lost_lead = await _lead(
        db, workspace.id, lost, days_on_stage=100, assigned_to=user.id,
        next_action_at=past, flags=True,
    )

    await _recompute(db, workspace.id)

    assert await _flags(db, won_lead) == (False, False)
    assert await _flags(db, lost_lead) == (False, False)


@skip_no_pg
async def test_next_step_overdue(db, workspace, user, pipeline):
    _, stage = pipeline
    overdue = await _lead(
        db, workspace.id, stage, days_on_stage=1, assigned_to=user.id,
        next_action_at=NOW - timedelta(hours=2),
    )
    upcoming = await _lead(
        db, workspace.id, stage, days_on_stage=1, assigned_to=user.id,
        next_action_at=NOW + timedelta(days=2),
    )
    none = await _lead(db, workspace.id, stage, days_on_stage=1, assigned_to=user.id)

    await _recompute(db, workspace.id)

    assert await _flags(db, overdue) == (False, True)
    assert await _flags(db, upcoming) == (False, False)
    assert await _flags(db, none) == (False, False)


@skip_no_pg
async def test_flags_cleared_when_condition_gone(db, workspace, user, pipeline):
    _, stage = pipeline
    lead = await _lead(
        db, workspace.id, stage, days_on_stage=2, assigned_to=user.id,
        next_action_at=NOW + timedelta(days=1), flags=True,
    )

    changed = await _recompute(db, workspace.id)

    assert changed == 1
    assert await _flags(db, lead) == (False, False)
    # Повторный проход ничего не переписывает.
    assert await _recompute(db, workspace.id) == 0


@skip_no_pg
async def test_pool_and_deleted_leads_not_flagged(db, workspace, user, pipeline):
    _, stage = pipeline
    past = NOW - timedelta(days=1)
    pool = await _lead(
        db, workspace.id, stage, days_on_stage=50, assigned_to=None, pool=True,
        next_action_at=past,
    )
    deleted = await _lead(
        db, workspace.id, stage, days_on_stage=50, assigned_to=user.id,
        next_action_at=past,
    )
    deleted.deleted_at = NOW
    await db.flush()

    await _recompute(db, workspace.id)

    assert await _flags(db, pool) == (False, False)
    assert await _flags(db, deleted) == (False, False)


@skip_no_pg
async def test_other_workspace_untouched(db, workspace, user, pipeline):
    from app.auth.models import Workspace

    _, stage = pipeline
    lead = await _lead(db, workspace.id, stage, days_on_stage=30, assigned_to=user.id)
    other = Workspace(name="Other WS", plan="pro", sprint_capacity_per_week=20)
    db.add(other)
    await db.flush()

    await _recompute(db, other.id)

    assert await _flags(db, lead) == (False, False)


@skip_no_pg
async def test_matches_forecast_at_risk(db, workspace, user, pipeline):
    """Застрявшие на этапе — те же лиды, что «под риском» в прогнозе."""
    from app.leads.analytics import _FORECAST_AT_RISK_SQL

    _, stage = pipeline
    leads = [
        await _lead(
            db, workspace.id, stage, days_on_stage=d, assigned_to=user.id, deal_amount=1000
        )
        for d in (3, 14, 15, 40)
    ]

    await _recompute(db, workspace.id)

    at_risk = {
        r["id"]
        for r in (
            await db.execute(
                _FORECAST_AT_RISK_SQL,
                {"wid": str(workspace.id), "assigned_to": None, "limit": 100},
            )
        ).mappings()
    }
    flagged = {str(lead.id) for lead in leads if (await _flags(db, lead))[0]}
    assert flagged == at_risk
    assert len(flagged) == 2


# --- Хук смены этапа --------------------------------------------------------

@skip_no_pg
async def test_move_stage_clears_stage_flag_keeps_overdue_step(db, workspace, user, pipeline):
    from app.automation.stage_change import move_stage

    p, stage = pipeline
    target = await _stage(db, p.id, rot_days=7)
    lead = await _lead(
        db, workspace.id, stage, days_on_stage=30, assigned_to=user.id,
        next_action_at=NOW - timedelta(days=1), flags=True,
    )

    await move_stage(db, lead, target, user.id)

    assert (lead.is_rotting_stage, lead.is_rotting_next_step) == (False, True)


@skip_no_pg
async def test_move_to_won_clears_both_flags(db, workspace, user, pipeline):
    from app.automation.stage_change import move_stage

    p, stage = pipeline
    won = await _stage(db, p.id, rot_days=7, is_won=True)
    lead = await _lead(
        db, workspace.id, stage, days_on_stage=30, assigned_to=user.id,
        next_action_at=NOW - timedelta(days=1), flags=True,
    )

    await move_stage(db, lead, won, user.id)

    assert (lead.is_rotting_stage, lead.is_rotting_next_step) == (False, False)


def test_rotting_task_in_beat_registry():
    from app.scheduled.celery_app import celery_app
    import app.scheduled.jobs  # noqa: F401

    entry = celery_app.conf.beat_schedule["recompute-lead-rotting"]
    assert entry["task"] == "app.scheduled.jobs.recompute_lead_rotting"
    assert entry["task"] in celery_app.tasks
