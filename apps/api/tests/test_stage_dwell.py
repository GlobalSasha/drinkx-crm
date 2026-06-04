"""Stage-dwell analytics — «где застревают сделки» (DB-backed)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import POSTGRES_AVAILABLE
from app.activity.models import Activity  # noqa: F401 — mapper config
from app.followups.models import Followup  # noqa: F401 — mapper config
from app.leads.models import Lead, LeadStageHistory
from app.pipelines.models import Stage
from app.leads.analytics import stage_dwell_summary

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires Postgres")

_DAY = 86400


def _lead(workspace_id, **kw):
    base = dict(workspace_id=workspace_id, company_name="Acme", assignment_status="pool", tags_json=[])
    base.update(kw)
    return Lead(**base)


def _hist(lead_id, stage_id, *, days_ago_entered, duration_days=None):
    now = datetime.now(timezone.utc)
    entered = now - timedelta(days=days_ago_entered)
    if duration_days is None:  # still open
        return LeadStageHistory(lead_id=lead_id, stage_id=stage_id, entered_at=entered)
    return LeadStageHistory(
        lead_id=lead_id,
        stage_id=stage_id,
        entered_at=entered,
        exited_at=entered + timedelta(days=duration_days),
        duration_sec=duration_days * _DAY,
    )


@skip_no_pg
async def test_stage_dwell_basic(db, workspace, pipeline):
    pipeline_obj, stage = pipeline  # rot_days=14 from the fixture
    lead = _lead(workspace.id)
    db.add(lead)
    await db.flush()

    # 3 completed visits: 1, 2, 3 days → median 2, avg 2.
    db.add_all([
        _hist(lead.id, stage.id, days_ago_entered=30, duration_days=1),
        _hist(lead.id, stage.id, days_ago_entered=25, duration_days=2),
        _hist(lead.id, stage.id, days_ago_entered=20, duration_days=3),
    ])
    # One lead stuck (open 20d > rot_days 14) and one fresh (open 2d, not stuck).
    db.add(_hist(lead.id, stage.id, days_ago_entered=20))
    db.add(_hist(lead.id, stage.id, days_ago_entered=2))
    await db.flush()

    rows = await stage_dwell_summary(db, workspace.id)
    row = next(r for r in rows if r["stage_id"] == str(stage.id))
    assert row["completed_count"] == 3
    assert row["median_days"] == 2.0
    assert row["avg_days"] == 2.0
    assert row["stuck_count"] == 1


@skip_no_pg
async def test_stage_dwell_excludes_terminal_stages(db, workspace, pipeline):
    pipeline_obj, active = pipeline
    won = Stage(pipeline_id=pipeline_obj.id, name="Выиграно", position=9, is_won=True)
    db.add(won)
    await db.flush()
    lead = _lead(workspace.id)
    db.add(lead)
    await db.flush()
    db.add(_hist(lead.id, won.id, days_ago_entered=10, duration_days=5))
    await db.flush()

    rows = await stage_dwell_summary(db, workspace.id)
    assert all(r["stage_id"] != str(won.id) for r in rows)   # won stage excluded
    assert any(r["stage_id"] == str(active.id) for r in rows)  # active stage listed


@skip_no_pg
async def test_stage_dwell_empty_stage_listed_with_nulls(db, workspace, pipeline):
    _pipeline_obj, stage = pipeline
    rows = await stage_dwell_summary(db, workspace.id)
    row = next(r for r in rows if r["stage_id"] == str(stage.id))
    assert row["completed_count"] == 0
    assert row["median_days"] is None
    assert row["p90_days"] is None
    assert row["stuck_count"] == 0


@skip_no_pg
async def test_stage_dwell_workspace_scoped(db, workspace, pipeline):
    from app.auth.models import Workspace
    from app.pipelines.models import Pipeline

    _pipeline_obj, _stage = pipeline
    other_ws = Workspace(name="Other", plan="pro", sprint_capacity_per_week=20)
    db.add(other_ws)
    await db.flush()
    other_pipe = Pipeline(workspace_id=other_ws.id, name="Other", type="sales", position=0)
    db.add(other_pipe)
    await db.flush()
    other_stage = Stage(pipeline_id=other_pipe.id, name="Foreign", position=1, rot_days=14)
    db.add(other_stage)
    await db.flush()
    other_lead = _lead(other_ws.id, company_name="Foreign")
    db.add(other_lead)
    await db.flush()
    db.add(_hist(other_lead.id, other_stage.id, days_ago_entered=20))  # stuck, but other ws
    await db.flush()

    rows = await stage_dwell_summary(db, workspace.id)
    assert all(r["stage_id"] != str(other_stage.id) for r in rows)
