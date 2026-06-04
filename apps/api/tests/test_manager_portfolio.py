"""Manager deal portfolio analytics (DB-backed)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from tests.conftest import POSTGRES_AVAILABLE
from app.activity.models import Activity  # noqa: F401 — mapper config
from app.followups.models import Followup  # noqa: F401 — mapper config
from app.leads.models import Lead
from app.pipelines.models import Stage
from app.team.services import UserNotFound, manager_portfolio

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires Postgres")


def _active_lead(workspace_id, user_id, stage_id, **kw):
    base = dict(
        workspace_id=workspace_id,
        company_name="Acme",
        assignment_status="assigned",
        assigned_to=user_id,
        stage_id=stage_id,
        tags_json=[],
    )
    base.update(kw)
    return Lead(**base)


@skip_no_pg
async def test_portfolio_kpi_segments_priorities(db, workspace, user, pipeline):
    _p, stage = pipeline
    db.add_all([
        _active_lead(workspace.id, user.id, stage.id, segment="retail",
                     deal_amount=Decimal("100"), deal_quantity=2, priority="A"),
        _active_lead(workspace.id, user.id, stage.id, segment="retail",
                     deal_amount=Decimal("200"), deal_quantity=3, priority="B"),
        _active_lead(workspace.id, user.id, stage.id, segment="horeca",
                     deal_amount=Decimal("50"), deal_quantity=1, priority="A"),
    ])
    await db.flush()

    p = await manager_portfolio(db, workspace_id=workspace.id, user_id=user.id)

    assert p["kpi"]["active_count"] == 3
    assert float(p["kpi"]["total_amount"]) == 350
    assert p["kpi"]["total_quantity"] == 6
    assert p["kpi"]["avg_amount"] == pytest.approx(116.67, abs=0.01)
    assert p["kpi"]["new_7d"] == 3  # all just created

    seg = {r["segment"]: r for r in p["by_segment"]}
    assert seg["retail"]["count"] == 2
    assert float(seg["retail"]["amount"]) == 300
    assert seg["retail"]["quantity"] == 5
    assert seg["horeca"]["count"] == 1

    pri = {r["priority"]: r for r in p["by_priority"]}
    assert pri["A"]["count"] == 2
    assert float(pri["A"]["amount"]) == 150
    assert pri["B"]["count"] == 1


@skip_no_pg
async def test_portfolio_excludes_non_active(db, workspace, user, admin_user, pipeline):
    pipeline_obj, active = pipeline
    won = Stage(pipeline_id=pipeline_obj.id, name="Выиграно", position=9, is_won=True)
    db.add(won)
    await db.flush()

    db.add_all([
        _active_lead(workspace.id, user.id, active.id, deal_amount=Decimal("100")),  # counts
        # excluded: won stage
        _active_lead(workspace.id, user.id, won.id, deal_amount=Decimal("999")),
        # excluded: archived
        _active_lead(workspace.id, user.id, active.id, deal_amount=Decimal("999"),
                     archived_at=datetime.now(timezone.utc)),
        # excluded: assigned to another manager
        _active_lead(workspace.id, admin_user.id, active.id, deal_amount=Decimal("999")),
        # excluded: in pool (not assigned)
        Lead(workspace_id=workspace.id, company_name="Pool", assignment_status="pool",
             stage_id=active.id, tags_json=[], deal_amount=Decimal("999")),
    ])
    await db.flush()

    p = await manager_portfolio(db, workspace_id=workspace.id, user_id=user.id)
    assert p["kpi"]["active_count"] == 1
    assert float(p["kpi"]["total_amount"]) == 100


@skip_no_pg
async def test_portfolio_new_window_and_at_risk(db, workspace, user, pipeline):
    _p, stage = pipeline
    old = _active_lead(workspace.id, user.id, stage.id, deal_amount=Decimal("10"))
    old.created_at = datetime.now(timezone.utc) - timedelta(days=40)
    fresh = _active_lead(workspace.id, user.id, stage.id, deal_amount=Decimal("20"))
    rotting = _active_lead(workspace.id, user.id, stage.id, deal_amount=Decimal("70"),
                           is_rotting_stage=True)
    db.add_all([old, fresh, rotting])
    await db.flush()

    p = await manager_portfolio(db, workspace_id=workspace.id, user_id=user.id)
    assert p["kpi"]["active_count"] == 3
    assert p["kpi"]["new_7d"] == 2          # fresh + rotting; old (40d) excluded
    assert p["kpi"]["new_30d"] == 2
    assert p["kpi"]["at_risk_count"] == 1
    assert float(p["kpi"]["at_risk_amount"]) == 70


@skip_no_pg
async def test_portfolio_top_deals_ordered(db, workspace, user, pipeline):
    _p, stage = pipeline
    db.add_all([
        _active_lead(workspace.id, user.id, stage.id, company_name="Small", deal_amount=Decimal("10")),
        _active_lead(workspace.id, user.id, stage.id, company_name="Big", deal_amount=Decimal("900")),
        _active_lead(workspace.id, user.id, stage.id, company_name="Mid", deal_amount=Decimal("400")),
    ])
    await db.flush()

    p = await manager_portfolio(db, workspace_id=workspace.id, user_id=user.id)
    names = [d["company_name"] for d in p["top_deals"]]
    assert names[:3] == ["Big", "Mid", "Small"]


@skip_no_pg
async def test_portfolio_user_not_found(db, workspace):
    with pytest.raises(UserNotFound):
        await manager_portfolio(db, workspace_id=workspace.id, user_id=uuid.uuid4())
