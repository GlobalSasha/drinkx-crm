"""Company overview aggregates (Sprint CEO G4) — DB-backed."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import POSTGRES_AVAILABLE

# Trigger ORM mapper configuration (Lead string-referenced relationships).
from app.activity.models import Activity  # noqa: F401
from app.followups.models import Followup  # noqa: F401
from app.lead_sources.models import LeadSource  # noqa: F401

from app.company import repositories as repo
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


@skip_no_pg
async def test_inflow_labels_forms_and_manual_and_uses_local_days(db, workspace, user):
    from zoneinfo import ZoneInfo

    from app.leads.models import Lead

    leads = await _setup(db, workspace, user)
    moscow = ZoneInfo("Europe/Moscow")
    local_midnight = datetime.now(moscow).replace(hour=0, minute=0, second=0, microsecond=0)
    # 00:30 Moscow = 21:30 UTC the day before — must count as «today» locally.
    form_lead = Lead(
        workspace_id=workspace.id, company_name="Form", pipeline_id=leads[0].pipeline_id,
        stage_id=leads[0].stage_id, source="form:landing",
        created_at=(local_midnight + timedelta(minutes=30)).astimezone(timezone.utc),
    )
    manual_lead = Lead(
        workspace_id=workspace.id, company_name="Typed", pipeline_id=leads[0].pipeline_id,
        stage_id=leads[0].stage_id,
        created_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db.add_all([form_lead, manual_lead])
    await db.flush()

    out = await svc.inflow(db, workspace_id=workspace.id, tz="Europe/Moscow")
    today = out["today"]
    assert today == local_midnight.date()

    names = [s["name"] for s in out["sources"]]
    assert "Сайт" in names
    assert names[-1] == "Вручную и загрузка базы"          # manual bucket always last
    assert next(s for s in out["sources"] if s["name"] == "Яндекс Директ")["total"] == 3
    assert next(s for s in out["sources"] if s["name"] == "Вручную и загрузка базы")["is_manual"]

    site_today = [p for p in out["days"] if p["source"] == "Сайт" and p["bucket"] == today]
    assert site_today and site_today[0]["count"] == 1

    # Months roll up the same leads: everything here is within the last 12 months.
    assert sum(p["count"] for p in out["months"]) == len(leads) + 2


@skip_no_pg
async def test_inflow_falls_back_to_moscow_on_unknown_timezone(db, workspace, user):
    out = await svc.inflow(db, workspace_id=workspace.id, tz="Mars/Olympus")
    assert out["timezone"] == "Europe/Moscow"
    assert out["days"] == [] and out["sources"] == []


@skip_no_pg
async def test_inflow_reaction_counts_people_on_incoming_leads_only(db, workspace, user):
    from app.leads.models import Lead

    leads = await _setup(db, workspace, user)  # L1/L2/L4 paid (Директ), L3 «Выставка» (not paid)
    now = datetime.now(timezone.utc)
    p_id, st_id = leads[0].pipeline_id, leads[0].stage_id

    answered = Lead(workspace_id=workspace.id, company_name="Answered", pipeline_id=p_id,
                    stage_id=st_id, source="form:landing", created_at=now - timedelta(hours=5))
    waiting = Lead(workspace_id=workspace.id, company_name="Waiting", pipeline_id=p_id,
                   stage_id=st_id, source="form:landing", created_at=now - timedelta(hours=30))
    db.add_all([answered, waiting])
    await db.flush()
    db.add_all([
        # Automation task: no user → not a reaction.
        Activity(lead_id=answered.id, type="task", payload_json={"text": "auto"},
                 created_at=now - timedelta(hours=4, minutes=30)),
        # A manager's comment two hours after the lead arrived → the first touch.
        Activity(lead_id=answered.id, user_id=user.id, type="comment", payload_json={"text": "звонил"},
                 created_at=now - timedelta(hours=3)),
        # Touch on the not-paid «Выставка» lead: that lead isn't incoming, ignored.
        Activity(lead_id=leads[2].id, user_id=user.id, type="comment", payload_json={"text": "x"},
                 created_at=now - timedelta(days=9)),
    ])
    await db.flush()

    r = (await svc.inflow(db, workspace_id=workspace.id, tz="Europe/Moscow"))["reaction"]
    cur = r["current"]
    # Incoming in 30 days: 3 paid (L1, L2, L4) + 2 form leads; «Выставка» excluded.
    assert cur["total"] == 5
    assert cur["touched"] == 1
    assert cur["median_hours"] == 2.0
    assert cur["within_hour"] == 0
    assert r["waiting_count"] == 4                       # L1, L2, L4, Waiting
    assert r["waiting"][0]["company_name"] == "L2"       # oldest first (3 days)
    assert {w["company_name"] for w in r["waiting"]} == {"L1", "L2", "L4", "Waiting"}
    assert r["previous"] == {"total": 0, "touched": 0, "median_hours": None, "within_hour": 0}


@skip_no_pg
async def test_deleted_lead_is_out_of_every_overview_number(db, workspace, user):
    """Удалённая заявка не открывается (404), поэтому не должна ни считаться,
    ни попадать в списки со ссылкой на карточку."""
    from app.leads.models import Lead

    leads = await _setup(db, workspace, user)
    now = datetime.now(timezone.utc)
    deleted = Lead(workspace_id=workspace.id, company_name="ТЕСТ", pipeline_id=leads[0].pipeline_id,
                   stage_id=leads[2].stage_id, source="form:landing", assignment_status="assigned",
                   assigned_to=user.id, created_at=now - timedelta(days=25))
    db.add(deleted)
    await db.flush()

    before = await svc.inflow(db, workspace_id=workspace.id, tz="Europe/Moscow")
    assert "ТЕСТ" in {w["company_name"] for w in before["reaction"]["waiting"]}
    stuck_before = await repo.stuck_count(db, workspace_id=workspace.id)
    load_before = await repo.portfolio_per_user(db, workspace_id=workspace.id, user_ids=[user.id])

    deleted.deleted_at = now
    await db.flush()

    after = await svc.inflow(db, workspace_id=workspace.id, tz="Europe/Moscow")
    assert "ТЕСТ" not in {w["company_name"] for w in after["reaction"]["waiting"]}
    assert after["reaction"]["waiting_count"] == before["reaction"]["waiting_count"] - 1
    assert after["reaction"]["current"]["total"] == before["reaction"]["current"]["total"] - 1
    assert await repo.stuck_count(db, workspace_id=workspace.id) == stuck_before - 1
    load_after = await repo.portfolio_per_user(db, workspace_id=workspace.id, user_ids=[user.id])
    assert load_after[user.id]["in_work"] == load_before[user.id]["in_work"] - 1


# --- «Застряла» считается по действиям людей, а не по возрасту лида ---------


async def _old_lead(db, workspace, user, **overrides):
    """A 30-day-old assigned lead with no touch of any kind."""
    from app.pipelines.models import Pipeline, Stage
    from app.leads.models import Lead

    p = Pipeline(workspace_id=workspace.id, name="Sales", type="sales", position=0)
    db.add(p)
    await db.flush()
    intake = Stage(pipeline_id=p.id, name="Первый контакт", position=0, color="#ccc", rot_days=14)
    working = Stage(pipeline_id=p.id, name="В работе", position=1, color="#ccc", rot_days=14)
    db.add_all([intake, working])
    await db.flush()
    lead = Lead(
        workspace_id=workspace.id,
        company_name="Old Co",
        pipeline_id=p.id,
        stage_id=working.id,
        assignment_status="assigned",
        assigned_to=user.id,
        created_at=datetime.now(timezone.utc) - timedelta(days=30),
        **overrides,
    )
    db.add(lead)
    await db.flush()
    return lead


def _days_ago(days):
    return datetime.now(timezone.utc) - timedelta(days=days)


@skip_no_pg
async def test_old_lead_without_touches_is_stuck_since_creation(db, workspace, user):
    await _old_lead(db, workspace, user)

    out = await svc.attention(db, workspace_id=workspace.id)

    assert (await svc.summary(db, workspace_id=workspace.id, period="week"))["stuck_count"] == 1
    assert out["stuck"][0]["days_idle"] in (29, 30)  # now() = transaction start


@skip_no_pg
@pytest.mark.parametrize(
    "activity",
    [
        pytest.param({"type": "comment", "with_user": True}, id="comment"),
        pytest.param({"type": "task", "with_user": True}, id="task"),
        pytest.param({"type": "stage_change", "with_user": True}, id="stage_change"),
        pytest.param({"type": "file", "with_user": True}, id="file"),
        pytest.param({"type": "phone", "with_user": False}, id="call_without_user"),
        pytest.param(
            {"type": "email", "with_user": False, "direction": "outbound"},
            id="outbound_email_without_user",
        ),
    ],
)
async def test_recent_person_touch_unsticks_old_lead(db, workspace, user, activity):
    lead = await _old_lead(db, workspace, user)
    fields = dict(activity)
    with_user = fields.pop("with_user")
    db.add(Activity(
        lead_id=lead.id,
        user_id=user.id if with_user else None,
        created_at=_days_ago(1),
        payload_json={},
        **fields,
    ))
    await db.flush()

    out = await svc.summary(db, workspace_id=workspace.id, period="week")

    assert out["stuck_count"] == 0


@skip_no_pg
@pytest.mark.parametrize(
    "activity",
    [
        pytest.param({"type": "task", "with_user": False}, id="automation_task"),
        pytest.param({"type": "comment", "with_user": False}, id="automation_comment"),
        pytest.param({"type": "system", "with_user": True}, id="system_row"),
        pytest.param({"type": "score_update", "with_user": True}, id="score_update"),
        pytest.param(
            {"type": "email", "with_user": False, "direction": "inbound"},
            id="unanswered_client_email",
        ),
        pytest.param(
            {"type": "comment", "with_user": True, "archived_at": _days_ago(0)},
            id="deleted_comment",
        ),
    ],
)
async def test_non_person_activity_does_not_unstick_lead(db, workspace, user, activity):
    lead = await _old_lead(db, workspace, user)
    fields = dict(activity)
    with_user = fields.pop("with_user")
    db.add(Activity(
        lead_id=lead.id,
        user_id=user.id if with_user else None,
        created_at=_days_ago(1),
        payload_json={},
        **fields,
    ))
    await db.flush()

    out = await svc.summary(db, workspace_id=workspace.id, period="week")

    assert out["stuck_count"] == 1


@skip_no_pg
async def test_closing_an_automation_task_counts_as_a_touch(db, workspace, user):
    lead = await _old_lead(db, workspace, user)
    db.add(Activity(
        lead_id=lead.id,
        user_id=None,
        type="task",
        created_at=_days_ago(20),
        task_done=True,
        task_completed_at=_days_ago(1),
        payload_json={},
    ))
    await db.flush()

    out = await svc.summary(db, workspace_id=workspace.id, period="week")

    assert out["stuck_count"] == 0


@skip_no_pg
@pytest.mark.parametrize("field", ["assigned_at", "transferred_at"])
async def test_recently_handed_over_lead_is_not_stuck(db, workspace, user, field):
    await _old_lead(db, workspace, user, **{field: _days_ago(1)})

    out = await svc.summary(db, workspace_id=workspace.id, period="week")

    assert out["stuck_count"] == 0


@skip_no_pg
async def test_idle_days_run_from_the_latest_touch(db, workspace, user):
    lead = await _old_lead(db, workspace, user)
    db.add_all([
        Activity(lead_id=lead.id, user_id=user.id, type="comment", created_at=_days_ago(20), payload_json={}),
        Activity(lead_id=lead.id, user_id=user.id, type="comment", created_at=_days_ago(10), payload_json={}),
    ])
    await db.flush()

    attention = await svc.attention(db, workspace_id=workspace.id)
    team = await svc.managers(db, workspace_id=workspace.id, period="week")

    assert attention["stuck"][0]["days_idle"] in (9, 10)
    assert attention["managers"][0]["stuck"] == 1
    assert team["managers"][0]["stuck"] == 1
    assert team["managers"][0]["oldest_stuck_days"] in (9, 10)


# --- Первый этап воронки показываем отдельно от «застряли» ------------------


async def _pipeline_with_shifted_positions(db, workspace):
    """Positions start at 1, like production: the first stage is the earliest
    one of its pipeline, not position 0."""
    from app.pipelines.models import Pipeline, Stage

    p = Pipeline(workspace_id=workspace.id, name="Sales", type="sales", position=0)
    db.add(p)
    await db.flush()
    first = Stage(pipeline_id=p.id, name="Первый контакт", position=1, color="#ccc", rot_days=1)
    second = Stage(pipeline_id=p.id, name="Квалификация", position=2, color="#ccc", rot_days=2)
    db.add_all([first, second])
    await db.flush()
    return p, first, second


def _idle_lead(workspace, user, pipeline, stage, name, idle_days):
    from app.leads.models import Lead

    return Lead(
        workspace_id=workspace.id,
        company_name=name,
        pipeline_id=pipeline.id,
        stage_id=stage.id,
        assignment_status="assigned",
        assigned_to=user.id,
        created_at=_days_ago(idle_days),
    )


@skip_no_pg
async def test_idle_leads_on_first_stage_are_counted_apart_from_stuck(db, workspace, user):
    p, first, second = await _pipeline_with_shifted_positions(db, workspace)
    db.add_all([
        _idle_lead(workspace, user, p, first, "Не начат 1", 20),
        _idle_lead(workspace, user, p, first, "Не начат 2", 10),
        _idle_lead(workspace, user, p, first, "Свежий", 2),
        _idle_lead(workspace, user, p, second, "Застрял", 15),
    ])
    await db.flush()

    summary = await svc.summary(db, workspace_id=workspace.id, period="week")
    attention = await svc.attention(db, workspace_id=workspace.id)
    team = await svc.managers(db, workspace_id=workspace.id, period="week")

    assert summary["stuck_count"] == 1
    assert summary["first_stage_idle_count"] == 2
    assert [s["company_name"] for s in attention["stuck"]] == ["Застрял"]
    assert attention["managers"][0]["stuck"] == 1
    assert team["managers"][0]["stuck"] == 1
    assert team["managers"][0]["oldest_stuck_days"] in (14, 15)
    assert team["totals"]["stuck"] == 1
