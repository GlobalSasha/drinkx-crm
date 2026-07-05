"""External read services — DB-backed."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import POSTGRES_AVAILABLE

# Configure ORM mappers (string-referenced relationships).
from app.activity.models import Activity  # noqa: F401
from app.followups.models import Followup  # noqa: F401
from app.lead_sources.models import LeadSource  # noqa: F401

from app.external import services as svc

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires Postgres")


async def _seed(db, workspace, user):
    from app.pipelines.models import Pipeline, Stage
    from app.leads.models import Lead, LeadStageHistory

    p = Pipeline(workspace_id=workspace.id, name="Sales", type="sales", position=0)
    db.add(p); await db.flush()
    s0 = Stage(pipeline_id=p.id, name="Новые", position=0, color="#ccc", rot_days=14, probability=10)
    s1 = Stage(pipeline_id=p.id, name="В работе", position=1, color="#ccc", rot_days=14, probability=50)
    db.add_all([s0, s1]); await db.flush()

    now = datetime.now(timezone.utc)
    a = Lead(workspace_id=workspace.id, company_name="Alpha", pipeline_id=p.id, stage_id=s1.id,
             assignment_status="assigned", assigned_to=user.id, deal_amount=1000)
    b = Lead(workspace_id=workspace.id, company_name="Beta", pipeline_id=p.id, stage_id=s0.id,
             assignment_status="pool", deal_amount=500)
    db.add_all([a, b]); await db.flush()
    # open stage-history row for Alpha → stage_entered_at
    db.add(LeadStageHistory(lead_id=a.id, stage_id=s1.id, entered_at=now - timedelta(days=3)))
    await db.flush()
    return p, s0, s1, a, b


@skip_no_pg
async def test_list_leads_includes_pool_and_stage_entered_at(db, workspace, user):
    p, s0, s1, a, b = await _seed(db, workspace, user)
    page = await svc.list_leads(db, workspace.id, limit=50)
    names = {l.company_name for l in page.items}
    assert names == {"Alpha", "Beta"}  # pool lead included, unlike internal list_leads
    alpha = next(l for l in page.items if l.company_name == "Alpha")
    assert alpha.stage_entered_at is not None
    beta = next(l for l in page.items if l.company_name == "Beta")
    assert beta.stage_entered_at is None  # no history row


@skip_no_pg
async def test_list_leads_filters_by_pipeline_and_stage(db, workspace, user):
    p, s0, s1, a, b = await _seed(db, workspace, user)
    page = await svc.list_leads(db, workspace.id, stage_id=s1.id)
    assert [l.company_name for l in page.items] == ["Alpha"]


@skip_no_pg
async def test_lead_summary_shape(db, workspace, user):
    p, s0, s1, a, b = await _seed(db, workspace, user)
    summ = await svc.lead_summary(db, workspace.id, a.id)
    assert summ is not None
    assert summ.lead.company_name == "Alpha"
    assert summ.stage_name == "В работе"
    assert summ.days_in_stage is not None and summ.days_in_stage >= 3


@skip_no_pg
async def test_workspace_isolation(db, workspace, user):
    p, s0, s1, a, b = await _seed(db, workspace, user)
    other_ws = uuid.uuid4()
    assert await svc.get_lead(db, other_ws, a.id) is None


@skip_no_pg
async def test_pipeline_summary_counts_and_amounts(db, workspace, user):
    p, s0, s1, a, b = await _seed(db, workspace, user)
    summ = await svc.pipeline_summary(db, workspace.id, p.id)
    assert summ is not None
    by_stage = {s.stage_name: s for s in summ.stages}
    assert by_stage["В работе"].lead_count == 1
    assert float(by_stage["В работе"].total_amount) == 1000.0
    assert by_stage["Новые"].lead_count == 1
