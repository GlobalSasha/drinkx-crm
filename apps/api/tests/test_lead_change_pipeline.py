"""Тесты смены воронки лида: перенос в другую воронку и правила выбора стадии."""
from __future__ import annotations

import uuid
import pytest
from tests.conftest import POSTGRES_AVAILABLE

skip_no_pg = pytest.mark.skipif(
    not POSTGRES_AVAILABLE,
    reason="Requires a running Postgres at postgresql+asyncpg://drinkx:dev@localhost:5432/drinkx_test",
)


async def _make_lead(db, workspace_id, **kwargs):
    from app.leads import repositories as repo
    assignment_status = kwargs.pop("assignment_status", "assigned")
    assigned_to = kwargs.pop("assigned_to", None)
    payload = dict(company_name=f"Company {uuid.uuid4().hex[:6]}")
    payload.update(kwargs)
    return await repo.create_lead(db, workspace_id, payload,
                                  assigned_to=assigned_to,
                                  assignment_status=assignment_status)


async def _make_stage(db, pipeline_id, *, position=0, name=None, is_won=False, is_lost=False):
    from app.pipelines.models import Stage
    s = Stage(pipeline_id=pipeline_id, name=name or f"Stage-pos{position}-{uuid.uuid4().hex[:4]}",
              position=position, color="#aabbcc", rot_days=7, is_won=is_won, is_lost=is_lost)
    db.add(s)
    await db.flush()
    return s


async def _make_pipeline(db, workspace_id, *, name=None, position=0):
    from app.pipelines.models import Pipeline
    p = Pipeline(workspace_id=workspace_id,
                 name=name or f"Pipeline-{uuid.uuid4().hex[:6]}",
                 type="sales", position=position)
    db.add(p)
    await db.flush()
    return p


async def _stage_change_activities(db, lead_id):
    from sqlalchemy import select
    from app.activity.models import Activity
    res = await db.execute(
        select(Activity).where(Activity.lead_id == lead_id, Activity.type == "stage_change")
    )
    return list(res.scalars().all())


@skip_no_pg
async def test_change_pipeline_moves_lead_to_first_stage(db, workspace, user, pipeline):
    from app.leads import services
    p_a, stage_a = pipeline
    lead = await _make_lead(db, workspace.id, pipeline_id=p_a.id, stage_id=stage_a.id)

    p_b = await _make_pipeline(db, workspace.id)
    stage_b0 = await _make_stage(db, p_b.id, position=0)
    await _make_stage(db, p_b.id, position=1)

    await services.change_pipeline(db, workspace.id, user.id, lead.id, p_b.id)

    assert lead.pipeline_id == p_b.id
    assert lead.stage_id == stage_b0.id


@skip_no_pg
async def test_change_pipeline_honors_explicit_stage(db, workspace, user, pipeline):
    from app.leads import services
    p_a, stage_a = pipeline
    lead = await _make_lead(db, workspace.id, pipeline_id=p_a.id, stage_id=stage_a.id)

    p_b = await _make_pipeline(db, workspace.id)
    await _make_stage(db, p_b.id, position=0)
    stage_b1 = await _make_stage(db, p_b.id, position=1)

    await services.change_pipeline(db, workspace.id, user.id, lead.id, p_b.id,
                                   stage_id=stage_b1.id)

    assert lead.pipeline_id == p_b.id
    assert lead.stage_id == stage_b1.id


@skip_no_pg
async def test_change_pipeline_rejects_stage_from_another_pipeline(db, workspace, user, pipeline):
    from app.leads import services
    p_a, stage_a = pipeline
    lead = await _make_lead(db, workspace.id, pipeline_id=p_a.id, stage_id=stage_a.id)

    p_b = await _make_pipeline(db, workspace.id)
    await _make_stage(db, p_b.id, position=0)

    with pytest.raises(services.StageNotFound):
        await services.change_pipeline(db, workspace.id, user.id, lead.id, p_b.id,
                                       stage_id=stage_a.id)


@skip_no_pg
async def test_change_pipeline_rejects_foreign_workspace_pipeline(db, workspace, user, pipeline):
    from app.leads import services
    from app.auth.models import Workspace
    p_a, stage_a = pipeline
    lead = await _make_lead(db, workspace.id, pipeline_id=p_a.id, stage_id=stage_a.id)

    other_ws = Workspace(name=f"WS-{uuid.uuid4().hex[:6]}", plan="pro",
                         sprint_capacity_per_week=20)
    db.add(other_ws)
    await db.flush()
    p_other = await _make_pipeline(db, other_ws.id)

    with pytest.raises(services.PipelineNotFound):
        await services.change_pipeline(db, workspace.id, user.id, lead.id, p_other.id)


@skip_no_pg
async def test_change_pipeline_without_stages_raises(db, workspace, user, pipeline):
    from app.leads import services
    p_a, stage_a = pipeline
    lead = await _make_lead(db, workspace.id, pipeline_id=p_a.id, stage_id=stage_a.id)

    p_b = await _make_pipeline(db, workspace.id)

    with pytest.raises(services.StageNotFound):
        await services.change_pipeline(db, workspace.id, user.id, lead.id, p_b.id)


@skip_no_pg
async def test_change_pipeline_noop_writes_no_history(db, workspace, user, pipeline):
    from app.leads import services
    p_a, stage_a = pipeline
    lead = await _make_lead(db, workspace.id, pipeline_id=p_a.id, stage_id=stage_a.id)

    p_b = await _make_pipeline(db, workspace.id)
    await _make_stage(db, p_b.id, position=0)

    await services.change_pipeline(db, workspace.id, user.id, lead.id, p_b.id)
    first = await _stage_change_activities(db, lead.id)

    await services.change_pipeline(db, workspace.id, user.id, lead.id, p_b.id)
    second = await _stage_change_activities(db, lead.id)

    assert len(second) == len(first)


@skip_no_pg
async def test_change_pipeline_unknown_lead_raises(db, workspace, user, pipeline):
    from app.leads import services
    p_a, _ = pipeline
    p_b = await _make_pipeline(db, workspace.id)
    await _make_stage(db, p_b.id, position=0)

    with pytest.raises(services.LeadNotFound):
        await services.change_pipeline(db, workspace.id, user.id, uuid.uuid4(), p_b.id)
