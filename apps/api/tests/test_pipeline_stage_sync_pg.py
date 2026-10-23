"""Saving the pipeline editor must not move leads out of their stages.

Regression for 23.10.2026: the editor's save dropped and recreated every
stage, so `leads.stage_id` (ON DELETE SET NULL) went empty for the whole
pipeline and `lead_stage_history` (CASCADE) was wiped. Needs PostgreSQL.
"""
from __future__ import annotations

import pytest
from sqlalchemy import func, select

import app.main  # noqa: F401  — настраивает мапперы SQLAlchemy
from tests.conftest import POSTGRES_AVAILABLE

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires PostgreSQL")


async def _setup(db, workspace):
    from app.leads.models import Lead, LeadStageHistory
    from app.pipelines.models import Pipeline, Stage

    p = Pipeline(workspace_id=workspace.id, name="B2B", type="sales", position=0)
    db.add(p)
    await db.flush()
    first = Stage(pipeline_id=p.id, name="Первый контакт", position=0)
    qual = Stage(pipeline_id=p.id, name="Квалификация", position=1)
    empty = Stage(pipeline_id=p.id, name="Пустая", position=2)
    db.add_all([first, qual, empty])
    await db.flush()
    lead = Lead(
        workspace_id=workspace.id, company_name="Ромашка",
        assignment_status="pool", pipeline_id=p.id, stage_id=qual.id,
    )
    db.add(lead)
    await db.flush()
    db.add(LeadStageHistory(lead_id=lead.id, stage_id=qual.id))
    await db.flush()
    db.expunge_all()
    return p, first, qual, empty, lead


@skip_no_pg
@pytest.mark.asyncio
async def test_reorder_rename_add_remove_keeps_leads_and_history(db, workspace):
    from app.leads.models import Lead, LeadStageHistory
    from app.pipelines import services as svc

    p, first, qual, empty, lead = await _setup(db, workspace)

    saved = await svc.update_pipeline(
        db, pipeline_id=p.id, workspace_id=workspace.id,
        stages=[
            {"id": qual.id, "name": "Квалификация лида", "position": 0},
            {"id": first.id, "name": "Первый контакт", "position": 1},
            {"name": "Пилотный проект", "position": 2, "color": "#a1a1a6",
             "rot_days": 7, "probability": 10, "is_won": False, "is_lost": False,
             "gate_criteria_json": []},
        ],
    )

    by_name = {s.name: s for s in saved.stages}
    assert set(by_name) == {"Квалификация лида", "Первый контакт", "Пилотный проект"}
    assert by_name["Квалификация лида"].id == qual.id
    assert by_name["Квалификация лида"].position == 0
    assert empty.id not in {s.id for s in saved.stages}

    reloaded = (await db.execute(select(Lead).where(Lead.id == lead.id))).scalar_one()
    assert reloaded.stage_id == qual.id
    history = await db.scalar(
        select(func.count()).select_from(LeadStageHistory)
        .where(LeadStageHistory.lead_id == lead.id)
    )
    assert history == 1


@skip_no_pg
@pytest.mark.asyncio
async def test_removing_stage_with_leads_is_refused(db, workspace):
    from app.leads.models import Lead
    from app.pipelines import services as svc

    p, first, qual, empty, lead = await _setup(db, workspace)

    with pytest.raises(svc.StageHasLeads) as exc:
        await svc.update_pipeline(
            db, pipeline_id=p.id, workspace_id=workspace.id,
            stages=[{"id": first.id, "name": "Первый контакт", "position": 0}],
        )
    assert exc.value.name == "Квалификация" and exc.value.count == 1

    reloaded = (await db.execute(select(Lead).where(Lead.id == lead.id))).scalar_one()
    assert reloaded.stage_id == qual.id
