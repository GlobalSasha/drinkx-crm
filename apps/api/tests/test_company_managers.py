"""Company managers dashboard aggregates — DB-backed."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from tests.conftest import POSTGRES_AVAILABLE

# Trigger ORM mapper configuration (Lead string-referenced relationships).
from app.activity.models import Activity  # noqa: F401
from app.followups.models import Followup  # noqa: F401
from app.presence.models import PresenceMinute  # noqa: F401

from app.company import services as svc

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires Postgres")


async def _setup_manager_scenario(db, workspace, user):
    """Pipeline + stages, one rotting lead, overdue task, comment, KP file."""
    from app.pipelines.models import Pipeline, Stage
    from app.leads.models import Lead

    p = Pipeline(workspace_id=workspace.id, name="Sales", type="sales", position=0)
    db.add(p)
    await db.flush()

    working = Stage(
        pipeline_id=p.id, name="В работе", position=1, color="#ccc", rot_days=14
    )
    won = Stage(
        pipeline_id=p.id,
        name="Выиграно",
        position=2,
        color="#ccc",
        rot_days=14,
        is_won=True,
    )
    lost = Stage(
        pipeline_id=p.id,
        name="Проиграно",
        position=3,
        color="#ccc",
        rot_days=14,
        is_lost=True,
    )
    db.add_all([working, won, lost])
    await db.flush()

    now = datetime.now(timezone.utc)

    active = Lead(
        workspace_id=workspace.id,
        company_name="Active Co",
        pipeline_id=p.id,
        stage_id=working.id,
        assignment_status="assigned",
        assigned_to=user.id,
        created_at=now - timedelta(days=2),
        last_activity_at=now - timedelta(days=1),
        is_rotting_stage=False,
        is_rotting_next_step=False,
    )
    stuck = Lead(
        workspace_id=workspace.id,
        company_name="Stuck Co",
        pipeline_id=p.id,
        stage_id=working.id,
        assignment_status="assigned",
        assigned_to=user.id,
        created_at=now - timedelta(days=10),
        last_activity_at=now - timedelta(days=8),
        is_rotting_stage=True,
        is_rotting_next_step=False,
    )
    db.add_all([active, stuck])
    await db.flush()

    # Comment action + KP file + overdue open task on stuck lead.
    acts = [
        Activity(
            lead_id=active.id,
            user_id=user.id,
            type="comment",
            body="hello",
            payload_json={},
        ),
        Activity(
            lead_id=active.id,
            user_id=user.id,
            type="file",
            file_kind="kp",
            file_url="https://example.com/kp.pdf",
            payload_json={},
        ),
        Activity(
            lead_id=stuck.id,
            user_id=user.id,
            type="task",
            task_done=False,
            task_due_at=now - timedelta(days=1),
            body="call back",
            payload_json={},
        ),
    ]
    db.add_all(acts)
    await db.flush()
    return {"pipeline": p, "working": working, "active": active, "stuck": stuck}


@skip_no_pg
async def test_managers_metrics_and_stuck_alert(db, workspace, user):
    await _setup_manager_scenario(db, workspace, user)

    out = await svc.managers(db, workspace_id=workspace.id, period="week")

    assert set(out.keys()) == {"period", "totals", "alerts", "managers"}
    assert out["period"] == "week"
    assert len(out["managers"]) == 1

    m = out["managers"][0]
    assert m["user_id"] == user.id
    assert m["name"] == user.name
    assert m["role"] == "manager"
    assert m["new_leads"] == 1          # only «Active Co» (2 дня); «Stuck Co» создан 10 дней назад — вне недели
    assert m["in_work"] == 2            # both non-terminal assigned
    assert m["stuck"] == 1              # rotting lead
    assert m["tasks_overdue"] == 1
    assert m["actions"] >= 3            # comment + file + task
    assert m["kp_sent"] == 1
    assert m["oldest_stuck_days"] >= 1

    stuck_alerts = [a for a in out["alerts"] if a["type"] == "stuck"]
    assert len(stuck_alerts) == 1
    assert stuck_alerts[0]["user_id"] == user.id
    assert stuck_alerts[0]["count"] == 1

    assert out["totals"]["new_leads"] == 1
    assert out["totals"]["stuck"] == 1
    assert out["totals"]["kp_sent"] == 1


@skip_no_pg
async def test_manager_in_crm_now_is_not_reported_silent(db, workspace, user):
    """Заходит в CRM, но давно не трогал лидов → «не заходил» звучать не должно.

    Прод-случай 21.07.2026: последний вход — 20 минут назад, последнее
    действие по лиду — 12 дней назад. Панель писала «не заходил 12 дней».
    «Был активен» — это про присутствие в CRM, а не про работу с лидами.
    """
    await _setup_manager_scenario(db, workspace, user)

    now = datetime.now(timezone.utc)
    user.last_login_at = now - timedelta(minutes=20)
    # Отодвигаем все действия менеджера на 12 дней назад.
    await db.execute(
        text("UPDATE activities SET created_at = :ts WHERE user_id = :uid"),
        {"ts": now - timedelta(days=12), "uid": user.id},
    )
    await db.flush()

    out = await svc.managers(db, workspace_id=workspace.id, period="week")

    m = next(x for x in out["managers"] if x["user_id"] == user.id)
    assert (now - m["last_active_at"]) < timedelta(hours=1)
    assert [a for a in out["alerts"] if a["type"] == "silent"] == []


@skip_no_pg
async def test_managers_includes_idle_manager_with_zeros(db, workspace, user):
    from app.auth.models import User

    await _setup_manager_scenario(db, workspace, user)

    idle = User(
        workspace_id=workspace.id,
        email=f"idle-{uuid.uuid4().hex[:8]}@test.com",
        name="AAA Idle",  # sorts before "Manager" when minutes tie at 0
        role="manager",
    )
    db.add(idle)
    await db.flush()

    out = await svc.managers(db, workspace_id=workspace.id, period="week")

    by_id = {m["user_id"]: m for m in out["managers"]}
    assert user.id in by_id
    assert idle.id in by_id
    assert len(out["managers"]) == 2

    idle_row = by_id[idle.id]
    assert idle_row["active_minutes"] == 0
    assert idle_row["new_leads"] == 0
    assert idle_row["actions"] == 0
    assert idle_row["kp_sent"] == 0
    assert idle_row["stage_moves"] == 0
    assert idle_row["tasks_done"] == 0
    assert idle_row["tasks_overdue"] == 0
    assert idle_row["in_work"] == 0
    assert idle_row["stuck"] == 0
    assert idle_row["oldest_stuck_days"] == 0
    assert idle_row["active_daily"] == []
