"""Company overview aggregates (Sprint CEO G4) — DB-backed."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import POSTGRES_AVAILABLE

# Trigger ORM mapper configuration (Lead string-referenced relationships).
from app.activity.models import Activity  # noqa: F401
from app.followups.models import Followup  # noqa: F401
from app.lead_sources.models import LeadSource  # noqa: F401

from app.company import services as svc

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires Postgres")


async def _setup(db, workspace, user):
    """Pipeline (intake=0, working=1, won=2), two sources, four leads."""
    from app.pipelines.models import Pipeline, Stage
    from app.leads.models import Lead

    p = Pipeline(workspace_id=workspace.id, name="Sales", type="sales", position=0)
    db.add(p)
    await db.flush()
    intake = Stage(pipeline_id=p.id, name="Входящие", position=0, color="#ccc", rot_days=14)
    working = Stage(pipeline_id=p.id, name="В работе", position=1, color="#ccc", rot_days=14)
    won = Stage(pipeline_id=p.id, name="Выиграно", position=2, color="#ccc", rot_days=14, is_won=True)
    db.add_all([intake, working, won])
    await db.flush()

    paid = LeadSource(workspace_id=workspace.id, name="Яндекс Директ", is_paid=True, is_system=True)
    expo = LeadSource(workspace_id=workspace.id, name="Выставка", is_paid=False)
    db.add_all([paid, expo])
    await db.flush()

    now = datetime.now(timezone.utc)

    def mk(name, source, stage, created_days_ago, idle_days, assigned):
        return Lead(
            workspace_id=workspace.id,
            company_name=name,
            pipeline_id=p.id,
            stage_id=stage.id,
            source_id=source.id,
            created_at=now - timedelta(days=created_days_ago),
            last_activity_at=now - timedelta(days=idle_days),
            assignment_status="assigned" if assigned else "pool",
            assigned_to=user.id if assigned else None,
        )

    # L1 paid+intake+today (not qualified); L2 paid+working+3d (qualified);
    # L3 expo+working+10d idle, assigned (stuck); L4 paid+working+2d fresh, assigned.
    leads = [
        mk("L1", paid, intake, 0, 0, False),
        mk("L2", paid, working, 3, 3, False),
        mk("L3", expo, working, 10, 10, True),
        mk("L4", paid, working, 2, 0, True),
    ]
    db.add_all(leads)
    await db.flush()
    return leads


@skip_no_pg
async def test_summary_counts_and_ad_conversion(db, workspace, user):
    await _setup(db, workspace, user)
    out = await svc.summary(db, workspace_id=workspace.id, period="month")

    assert out["leads_today"] == 1          # L1
    assert out["leads_7d"] == 3             # L1, L2, L4 (L3 is 10d old)
    assert out["leads_7d_prior"] == 1       # L3 (10d) falls in [today-13, today-6)
    assert out["stuck_count"] == 1          # L3 only (assigned, 10d idle)

    # Paid (Директ) = L1,L2,L4 → 3 leads, qualified L2,L4 (position>0) → 2 → 66.7%
    assert out["ad_conversion_pct"] == 66.7
    # Prior month window [today-59, today-29) is empty → no paid leads → None
    assert out["ad_conversion_pct_prior"] is None

    by_name = {s["name"]: s for s in out["sources"]}
    assert by_name["Яндекс Директ"]["leads"] == 3
    assert by_name["Яндекс Директ"]["qualified"] == 2
    assert by_name["Выставка"]["leads"] == 1
    # Prior month window empty → every source's prev_leads is 0
    assert all(s["prev_leads"] == 0 for s in out["sources"])
    assert len(out["daily"]) >= 3           # L1..L4 all within 14d


@skip_no_pg
async def test_attention_stuck_and_managers(db, workspace, user):
    await _setup(db, workspace, user)
    out = await svc.attention(db, workspace_id=workspace.id)

    assert len(out["stuck"]) == 1
    s = out["stuck"][0]
    assert s["company_name"] == "L3"
    assert s["source_name"] == "Выставка"
    assert s["manager_name"] == user.name
    assert s["stage_name"] == "В работе"     # the "why" hint
    assert s["days_idle"] >= 7
    assert out["oldest_days_idle"] >= 7      # MAX across stuck

    assert len(out["managers"]) == 1
    m = out["managers"][0]
    assert m["user_id"] == user.id
    assert m["max_active_deals"] == 20       # User default capacity
    assert m["in_work"] == 2                 # L3 + L4
    assert m["stuck"] == 1                   # L3
    assert m["new_week"] == 1                # L4 (2d); L3 is 10d
