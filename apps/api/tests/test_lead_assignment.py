"""Раздача лидов из базы: руководитель выдаёт карточки менеджеру.

Покрывает POST /leads/assign — оба режима (список id и фильтр по пулу),
перехват чужой карточки с сохранением истории, идемпотентность и
изоляцию рабочих пространств.
"""
from __future__ import annotations

import uuid

import pytest

from tests.conftest import POSTGRES_AVAILABLE

skip_no_pg = pytest.mark.skipif(
    not POSTGRES_AVAILABLE,
    reason="Requires a running Postgres at postgresql+asyncpg://drinkx:dev@localhost:5432/drinkx_test",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _make_user(db, workspace_id, role: str, name: str):
    from app.auth.models import User

    u = User(
        workspace_id=workspace_id,
        email=f"{name}-{uuid.uuid4().hex[:6]}@example.com",
        name=name,
        role=role,
    )
    db.add(u)
    await db.flush()
    return u


async def _make_lead(db, workspace_id, **kwargs):
    from app.leads import repositories as repo

    assignment_status = kwargs.pop("assignment_status", "pool")
    assigned_to = kwargs.pop("assigned_to", None)
    payload = dict(company_name=f"Company {uuid.uuid4().hex[:6]}")
    payload.update(kwargs)
    return await repo.create_lead(
        db,
        workspace_id,
        payload,
        assigned_to=assigned_to,
        assignment_status=assignment_status,
    )


async def _assign(db, workspace, actor, target, **kwargs):
    from app.leads import services

    params = dict(
        lead_ids=[], cities=[], segment=None, fit_min=None, limit=None, comment=None
    )
    params.update(kwargs)
    return await services.assign_leads(
        db, workspace.id, actor.id, target.id, **params
    )


# ---------------------------------------------------------------------------
# Роль
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_manager_cannot_reach_the_assign_endpoint():
    """Обычный менеджер получает 403 на выдаче лидов — он берёт
    карточки себе через /claim, а не раздаёт другим."""
    from types import SimpleNamespace

    from fastapi import HTTPException

    from app.auth.dependencies import require_admin_or_head

    with pytest.raises(HTTPException) as exc:
        await require_admin_or_head(user=SimpleNamespace(role="manager"))
    assert exc.value.status_code == 403

    for role in ("admin", "head"):
        allowed = await require_admin_or_head(user=SimpleNamespace(role=role))
        assert allowed.role == role


# ---------------------------------------------------------------------------
# Режим «список id»
# ---------------------------------------------------------------------------

@skip_no_pg
@pytest.mark.asyncio
async def test_head_assigns_explicit_leads_to_a_manager(db, workspace):
    head = await _make_user(db, workspace.id, "head", "Head")
    manager = await _make_user(db, workspace.id, "manager", "Kirill")
    leads = [await _make_lead(db, workspace.id) for _ in range(3)]

    assigned, requested, skipped = await _assign(
        db, workspace, head, manager, lead_ids=[lead.id for lead in leads]
    )

    assert len(assigned) == 3
    assert requested == 3
    assert skipped == 0
    for lead in assigned:
        assert lead.assigned_to == manager.id
        assert lead.assignment_status == "assigned"
        assert lead.assigned_at is not None


@skip_no_pg
@pytest.mark.asyncio
async def test_reassignment_keeps_the_previous_owner_in_history(db, workspace):
    """Карточку, занятую другим менеджером, руководитель забрать может —
    но прежний владелец обязан остаться в transferred_from, иначе
    история передач рвётся."""
    head = await _make_user(db, workspace.id, "head", "Head")
    old_owner = await _make_user(db, workspace.id, "manager", "Old")
    new_owner = await _make_user(db, workspace.id, "manager", "New")
    lead = await _make_lead(
        db, workspace.id, assignment_status="assigned", assigned_to=old_owner.id
    )

    assigned, _, _ = await _assign(db, workspace, head, new_owner, lead_ids=[lead.id])

    assert len(assigned) == 1
    assert assigned[0].assigned_to == new_owner.id
    assert assigned[0].transferred_from == old_owner.id
    assert assigned[0].transferred_at is not None


@skip_no_pg
@pytest.mark.asyncio
async def test_assigning_to_the_current_owner_is_a_no_op(db, workspace):
    """Повторная выдача той же карточки тому же человеку ничего не
    меняет и считается пропуском — кнопку можно нажать дважды."""
    head = await _make_user(db, workspace.id, "head", "Head")
    manager = await _make_user(db, workspace.id, "manager", "Kirill")
    lead = await _make_lead(
        db, workspace.id, assignment_status="assigned", assigned_to=manager.id
    )

    assigned, requested, skipped = await _assign(
        db, workspace, head, manager, lead_ids=[lead.id]
    )

    assert assigned == []
    assert requested == 1
    assert skipped == 1
    assert lead.transferred_from is None


@skip_no_pg
@pytest.mark.asyncio
async def test_deleted_leads_are_not_handed_out(db, workspace):
    head = await _make_user(db, workspace.id, "head", "Head")
    manager = await _make_user(db, workspace.id, "manager", "Kirill")
    alive = await _make_lead(db, workspace.id)
    trashed = await _make_lead(db, workspace.id)

    from app.leads import repositories as repo

    await repo.soft_delete_lead(db, trashed, head.id)

    assigned, requested, skipped = await _assign(
        db, workspace, head, manager, lead_ids=[alive.id, trashed.id]
    )

    assert [lead.id for lead in assigned] == [alive.id]
    assert requested == 2
    assert skipped == 1


# ---------------------------------------------------------------------------
# Режим «по фильтру»
# ---------------------------------------------------------------------------

@skip_no_pg
@pytest.mark.asyncio
async def test_filter_mode_takes_only_pool_leads_and_respects_the_limit(db, workspace):
    """Раздача по фильтру не вырывает карточки у менеджеров: берётся
    только пул, и не больше запрошенного количества."""
    head = await _make_user(db, workspace.id, "head", "Head")
    manager = await _make_user(db, workspace.id, "manager", "Kirill")
    other = await _make_user(db, workspace.id, "manager", "Other")

    for _ in range(4):
        await _make_lead(db, workspace.id, city="Москва")
    busy = await _make_lead(
        db,
        workspace.id,
        city="Москва",
        assignment_status="assigned",
        assigned_to=other.id,
    )

    assigned, requested, skipped = await _assign(
        db, workspace, head, manager, cities=["Москва"], limit=2
    )

    assert len(assigned) == 2
    assert requested == 2
    assert skipped == 0
    assert busy.id not in {lead.id for lead in assigned}
    assert busy.assigned_to == other.id


@skip_no_pg
@pytest.mark.asyncio
async def test_filter_mode_reports_a_shortfall_when_the_pool_runs_dry(db, workspace):
    head = await _make_user(db, workspace.id, "head", "Head")
    manager = await _make_user(db, workspace.id, "manager", "Kirill")
    await _make_lead(db, workspace.id, city="Казань")

    assigned, requested, skipped = await _assign(
        db, workspace, head, manager, cities=["Казань"], limit=5
    )

    assert len(assigned) == 1
    assert requested == 5
    assert skipped == 4


@skip_no_pg
@pytest.mark.asyncio
async def test_filter_mode_falls_back_to_the_workspace_sprint_capacity(db, workspace):
    """Без явного количества берём недельную норму спринта из настроек
    рабочего пространства — то же правило, что у менеджерского спринта."""
    head = await _make_user(db, workspace.id, "head", "Head")
    manager = await _make_user(db, workspace.id, "manager", "Kirill")

    _, requested, _ = await _assign(db, workspace, head, manager)

    assert requested == workspace.sprint_capacity_per_week


# ---------------------------------------------------------------------------
# Изоляция и побочные эффекты
# ---------------------------------------------------------------------------

@skip_no_pg
@pytest.mark.asyncio
async def test_target_from_another_workspace_is_rejected(db, workspace):
    from app.auth.models import Workspace
    from app.leads.services import TransferTargetInvalid

    head = await _make_user(db, workspace.id, "head", "Head")
    other_ws = Workspace(name="Other WS", plan="free")
    db.add(other_ws)
    await db.flush()
    outsider = await _make_user(db, other_ws.id, "manager", "Outsider")
    lead = await _make_lead(db, workspace.id)

    with pytest.raises(TransferTargetInvalid):
        await _assign(db, workspace, head, outsider, lead_ids=[lead.id])

    assert lead.assigned_to is None


@skip_no_pg
@pytest.mark.asyncio
async def test_a_batch_produces_one_notification_not_one_per_lead(db, workspace):
    """Двадцать карточек — одно уведомление. Иначе колокольчик
    превращается в мусор."""
    from sqlalchemy import select

    from app.notifications.models import Notification

    head = await _make_user(db, workspace.id, "head", "Head")
    manager = await _make_user(db, workspace.id, "manager", "Kirill")
    leads = [await _make_lead(db, workspace.id) for _ in range(5)]

    await _assign(db, workspace, head, manager, lead_ids=[lead.id for lead in leads])

    rows = (
        await db.execute(
            select(Notification).where(
                Notification.user_id == manager.id,
                Notification.kind == "leads_assigned",
            )
        )
    ).scalars().all()
    assert len(rows) == 1
    assert "5" in rows[0].title


@skip_no_pg
@pytest.mark.asyncio
async def test_two_batches_in_a_row_both_reach_the_manager(db, workspace):
    """Часовое окно дедупликации не должно глушить вторую раздачу."""
    from sqlalchemy import select

    from app.notifications.models import Notification

    head = await _make_user(db, workspace.id, "head", "Head")
    manager = await _make_user(db, workspace.id, "manager", "Kirill")
    first = await _make_lead(db, workspace.id)
    second = await _make_lead(db, workspace.id)

    await _assign(db, workspace, head, manager, lead_ids=[first.id])
    await _assign(db, workspace, head, manager, lead_ids=[second.id])

    rows = (
        await db.execute(
            select(Notification).where(
                Notification.user_id == manager.id,
                Notification.kind == "leads_assigned",
            )
        )
    ).scalars().all()
    assert len(rows) == 2


@skip_no_pg
@pytest.mark.asyncio
async def test_each_handed_out_lead_gets_a_feed_entry(db, workspace):
    from sqlalchemy import select

    from app.activity.models import Activity, ActivityType

    head = await _make_user(db, workspace.id, "head", "Head")
    manager = await _make_user(db, workspace.id, "manager", "Kirill")
    leads = [await _make_lead(db, workspace.id) for _ in range(2)]

    await _assign(db, workspace, head, manager, lead_ids=[lead.id for lead in leads])
    await db.flush()

    rows = (
        await db.execute(
            select(Activity).where(
                Activity.lead_id.in_([lead.id for lead in leads]),
                Activity.type == ActivityType.lead_assigned.value,
            )
        )
    ).scalars().all()
    assert len(rows) == 2
    assert {row.payload_json.get("source") for row in rows} == {"head_assign"}
