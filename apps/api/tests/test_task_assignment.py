"""Задачи с исполнителем и задачи без лида (миграция 0058).

До этого исполнителем задачи молча считался владелец лида, а задача
обязана была относиться к лиду. Тесты закрепляют обе новые возможности
и обратную совместимость старых строк (assignee_user_id IS NULL).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import POSTGRES_AVAILABLE

skip_no_pg = pytest.mark.skipif(
    not POSTGRES_AVAILABLE,
    reason="Requires a running Postgres at postgresql+asyncpg://drinkx:dev@localhost:5432/drinkx_test",
)

TOMORROW = datetime.now(timezone.utc) + timedelta(days=1)
YESTERDAY = datetime.now(timezone.utc) - timedelta(days=1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _make_user(db, workspace_id, role: str, name: str):
    from app.auth.models import User

    u = User(
        workspace_id=workspace_id,
        email=f"{name.lower()}-{uuid.uuid4().hex[:6]}@example.com",
        name=name,
        role=role,
    )
    db.add(u)
    await db.flush()
    return u


async def _make_lead(db, workspace_id, **kwargs):
    from app.leads import repositories as repo

    assignment_status = kwargs.pop("assignment_status", "assigned")
    assigned_to = kwargs.pop("assigned_to", None)
    payload = dict(company_name=f"Company {uuid.uuid4().hex[:6]}")
    payload.update(kwargs)
    return await repo.create_lead(
        db, workspace_id, payload,
        assigned_to=assigned_to,
        assignment_status=assignment_status,
    )


async def _create_task(db, workspace, actor, **kwargs):
    from app.activity import services

    params = dict(
        text="Позвонить", task_due_at=TOMORROW, assignee_user_id=None, lead_id=None
    )
    params.update(kwargs)
    return await services.create_task(db, workspace.id, actor, **params)


async def _my_tasks(db, workspace, user):
    from app.activity import services

    return await services.list_my_tasks(
        db, workspace_id=workspace.id, user_id=user.id
    )


# ---------------------------------------------------------------------------
# Кто исполнитель — чистая логика, без базы
# ---------------------------------------------------------------------------

def test_effective_assignee_falls_back_from_explicit_to_owner_to_author():
    """Лестница разрешения исполнителя: явный → владелец лида → автор.
    Средняя ступень — это то, как задачи работали до появления поля."""
    from types import SimpleNamespace

    from app.activity.services import effective_assignee_id

    explicit, owner, author = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    lead = SimpleNamespace(assigned_to=owner)

    assert effective_assignee_id(
        SimpleNamespace(assignee_user_id=explicit, user_id=author), lead
    ) == explicit
    assert effective_assignee_id(
        SimpleNamespace(assignee_user_id=None, user_id=author), lead
    ) == owner
    assert effective_assignee_id(
        SimpleNamespace(assignee_user_id=None, user_id=author), None
    ) == author
    assert effective_assignee_id(
        SimpleNamespace(assignee_user_id=None, user_id=author),
        SimpleNamespace(assigned_to=None),
    ) == author


# ---------------------------------------------------------------------------
# Постановка задачи
# ---------------------------------------------------------------------------

@skip_no_pg
@pytest.mark.asyncio
async def test_head_assigns_a_task_to_a_manager(db, workspace):
    head = await _make_user(db, workspace.id, "head", "Head")
    manager = await _make_user(db, workspace.id, "manager", "Kirill")

    task = await _create_task(
        db, workspace, head, text="Обзвонить сети", assignee_user_id=manager.id
    )

    assert task.assignee_user_id == manager.id
    assert task.user_id == head.id
    assert task.lead_id is None
    assert task.workspace_id == workspace.id

    rows = await _my_tasks(db, workspace, manager)
    assert [r["text"] for r in rows] == ["Обзвонить сети"]
    assert rows[0]["author_name"] == "Head"
    assert rows[0]["assignee_name"] == "Kirill"


@skip_no_pg
@pytest.mark.asyncio
async def test_manager_cannot_hand_a_task_to_a_colleague(db, workspace):
    """Ставить задачи другим — право руководителя. Менеджер заводит
    задачи только себе."""
    from app.activity.services import ActivityForbidden

    manager = await _make_user(db, workspace.id, "manager", "Kirill")
    peer = await _make_user(db, workspace.id, "manager", "Peer")

    with pytest.raises(ActivityForbidden):
        await _create_task(db, workspace, manager, assignee_user_id=peer.id)


@skip_no_pg
@pytest.mark.asyncio
async def test_manager_can_create_a_task_for_himself(db, workspace):
    manager = await _make_user(db, workspace.id, "manager", "Kirill")

    task = await _create_task(db, workspace, manager, assignee_user_id=manager.id)

    assert task.assignee_user_id == manager.id
    assert len(await _my_tasks(db, workspace, manager)) == 1


@skip_no_pg
@pytest.mark.asyncio
async def test_assignee_from_another_workspace_is_rejected(db, workspace):
    from app.activity.services import TaskAssigneeInvalid
    from app.auth.models import Workspace

    head = await _make_user(db, workspace.id, "head", "Head")
    other_ws = Workspace(name="Other WS", plan="free")
    db.add(other_ws)
    await db.flush()
    outsider = await _make_user(db, other_ws.id, "manager", "Outsider")

    with pytest.raises(TaskAssigneeInvalid):
        await _create_task(db, workspace, head, assignee_user_id=outsider.id)


# ---------------------------------------------------------------------------
# Обратная совместимость: старые задачи без исполнителя
# ---------------------------------------------------------------------------

@skip_no_pg
@pytest.mark.asyncio
async def test_a_task_without_an_assignee_belongs_to_the_lead_owner(db, workspace):
    """Так задачи работали до 0058 — строки с NULL должны читаться
    по-старому, иначе у менеджеров пропадёт весь накопленный список."""
    from app.activity import repositories as activity_repo

    head = await _make_user(db, workspace.id, "head", "Head")
    manager = await _make_user(db, workspace.id, "manager", "Kirill")
    lead = await _make_lead(db, workspace.id, assigned_to=manager.id)

    await activity_repo.create(
        db, lead.id, head.id,
        dict(type="task", payload_json={"title": "Старая задача"}, task_due_at=TOMORROW),
    )

    rows = await _my_tasks(db, workspace, manager)
    assert [r["text"] for r in rows] == ["Старая задача"]
    assert rows[0]["assignee_user_id"] == manager.id
    assert rows[0]["assignee_name"] == "Kirill"


@skip_no_pg
@pytest.mark.asyncio
async def test_the_lead_owner_can_close_a_task_the_head_created(db, workspace):
    """Регрессия: менеджер видел в своём списке задачу, поставленную
    руководителем на его лид, но закрыть её не мог — проверка прав
    пропускала только автора."""
    from app.activity import repositories as activity_repo
    from app.activity import services

    head = await _make_user(db, workspace.id, "head", "Head")
    manager = await _make_user(db, workspace.id, "manager", "Kirill")
    lead = await _make_lead(db, workspace.id, assigned_to=manager.id)
    task = await activity_repo.create(
        db, lead.id, head.id,
        dict(type="task", payload_json={"title": "Съездить"}, task_due_at=TOMORROW),
    )

    done = await services.complete_task(db, workspace.id, lead.id, task.id, manager)

    assert done.task_done is True


@skip_no_pg
@pytest.mark.asyncio
async def test_a_managers_task_on_a_colleagues_lead_stays_on_the_manager(db, workspace):
    """Менеджер без явного исполнителя ставит задачу себе, даже если
    лид принадлежит коллеге — иначе задача уедет владельцу карточки в
    обход правила «ставить другим может только руководитель»."""
    manager = await _make_user(db, workspace.id, "manager", "Kirill")
    peer = await _make_user(db, workspace.id, "manager", "Peer")
    lead = await _make_lead(db, workspace.id, assigned_to=peer.id)

    task = await _create_task(db, workspace, manager, lead_id=lead.id)

    assert task.assignee_user_id == manager.id
    assert await _my_tasks(db, workspace, peer) == []


@skip_no_pg
@pytest.mark.asyncio
async def test_an_explicit_assignee_beats_the_lead_owner(db, workspace):
    """Задача на чужом лиде: делает тот, на кого её повесили, а не
    владелец карточки."""
    head = await _make_user(db, workspace.id, "head", "Head")
    owner = await _make_user(db, workspace.id, "manager", "Owner")
    doer = await _make_user(db, workspace.id, "manager", "Doer")
    lead = await _make_lead(db, workspace.id, assigned_to=owner.id)

    await _create_task(
        db, workspace, head, lead_id=lead.id, assignee_user_id=doer.id
    )

    assert len(await _my_tasks(db, workspace, doer)) == 1
    assert await _my_tasks(db, workspace, owner) == []


# ---------------------------------------------------------------------------
# Списки и фильтры
# ---------------------------------------------------------------------------

@skip_no_pg
@pytest.mark.asyncio
async def test_a_manager_does_not_see_another_managers_tasks(db, workspace):
    from app.activity import services

    head = await _make_user(db, workspace.id, "head", "Head")
    manager = await _make_user(db, workspace.id, "manager", "Kirill")
    peer = await _make_user(db, workspace.id, "manager", "Peer")

    await _create_task(db, workspace, head, text="Кириллу", assignee_user_id=manager.id)
    await _create_task(db, workspace, head, text="Петру", assignee_user_id=peer.id)

    rows = await services.list_tasks(db, workspace_id=workspace.id, actor=manager)
    assert [r["text"] for r in rows] == ["Кириллу"]


@skip_no_pg
@pytest.mark.asyncio
async def test_the_head_sees_the_team_and_can_filter_by_assignee(db, workspace):
    from app.activity import services

    head = await _make_user(db, workspace.id, "head", "Head")
    manager = await _make_user(db, workspace.id, "manager", "Kirill")
    peer = await _make_user(db, workspace.id, "manager", "Peer")

    await _create_task(db, workspace, head, text="Кириллу", assignee_user_id=manager.id)
    await _create_task(db, workspace, head, text="Петру", assignee_user_id=peer.id)

    everyone = await services.list_tasks(db, workspace_id=workspace.id, actor=head)
    assert {r["text"] for r in everyone} == {"Кириллу", "Петру"}

    only_kirill = await services.list_tasks(
        db, workspace_id=workspace.id, actor=head, assignee_user_id=manager.id
    )
    assert [r["text"] for r in only_kirill] == ["Кириллу"]


@skip_no_pg
@pytest.mark.asyncio
async def test_the_head_can_list_what_he_set_himself(db, workspace):
    from app.activity import services

    head = await _make_user(db, workspace.id, "head", "Head")
    other_head = await _make_user(db, workspace.id, "head", "Other")
    manager = await _make_user(db, workspace.id, "manager", "Kirill")

    await _create_task(db, workspace, head, text="Моя", assignee_user_id=manager.id)
    await _create_task(db, workspace, other_head, text="Чужая", assignee_user_id=manager.id)

    rows = await services.list_tasks(
        db, workspace_id=workspace.id, actor=head, author_user_id=head.id
    )
    assert [r["text"] for r in rows] == ["Моя"]


@skip_no_pg
@pytest.mark.asyncio
async def test_the_overdue_filter_skips_open_future_and_closed_tasks(db, workspace):
    from app.activity import services

    head = await _make_user(db, workspace.id, "head", "Head")
    manager = await _make_user(db, workspace.id, "manager", "Kirill")

    await _create_task(
        db, workspace, head, text="Просрочена",
        task_due_at=YESTERDAY, assignee_user_id=manager.id,
    )
    await _create_task(
        db, workspace, head, text="Впереди",
        task_due_at=TOMORROW, assignee_user_id=manager.id,
    )
    closed = await _create_task(
        db, workspace, head, text="Закрыта",
        task_due_at=YESTERDAY, assignee_user_id=manager.id,
    )
    await services.set_task_done_by_id(
        db, workspace.id, closed.id, manager, done=True
    )

    rows = await services.list_tasks(
        db, workspace_id=workspace.id, actor=head, status="overdue"
    )
    assert [r["text"] for r in rows] == ["Просрочена"]


@skip_no_pg
@pytest.mark.asyncio
async def test_tasks_on_trashed_leads_stay_out_of_the_lists(db, workspace):
    from app.activity import services
    from app.leads import repositories as leads_repo

    head = await _make_user(db, workspace.id, "head", "Head")
    manager = await _make_user(db, workspace.id, "manager", "Kirill")
    lead = await _make_lead(db, workspace.id, assigned_to=manager.id)
    await _create_task(db, workspace, head, lead_id=lead.id, assignee_user_id=manager.id)

    assert len(await _my_tasks(db, workspace, manager)) == 1

    await leads_repo.soft_delete_lead(db, lead, head.id)
    await db.flush()

    assert await _my_tasks(db, workspace, manager) == []
    assert await services.list_tasks(db, workspace_id=workspace.id, actor=head) == []


@skip_no_pg
@pytest.mark.asyncio
async def test_tasks_do_not_leak_across_workspaces(db, workspace):
    from app.activity import services
    from app.auth.models import Workspace

    other_ws = Workspace(name="Other WS", plan="free")
    db.add(other_ws)
    await db.flush()
    outsider = await _make_user(db, other_ws.id, "head", "Outsider")
    await _create_task(db, other_ws, outsider, text="Чужая задача")

    head = await _make_user(db, workspace.id, "head", "Head")
    assert await services.list_tasks(db, workspace_id=workspace.id, actor=head) == []


# ---------------------------------------------------------------------------
# Правка и уведомления
# ---------------------------------------------------------------------------

@skip_no_pg
@pytest.mark.asyncio
async def test_the_assignee_is_notified_once_the_task_lands(db, workspace):
    from sqlalchemy import select

    from app.notifications.models import Notification

    head = await _make_user(db, workspace.id, "head", "Head")
    manager = await _make_user(db, workspace.id, "manager", "Kirill")

    await _create_task(
        db, workspace, head, text="Съездить в Ашан", assignee_user_id=manager.id
    )

    rows = (
        await db.execute(
            select(Notification).where(
                Notification.user_id == manager.id,
                Notification.kind == "task_assigned",
            )
        )
    ).scalars().all()
    assert len(rows) == 1
    assert "Ашан" in rows[0].body


@skip_no_pg
@pytest.mark.asyncio
async def test_a_task_you_set_yourself_does_not_ping_you(db, workspace):
    from sqlalchemy import select

    from app.notifications.models import Notification

    manager = await _make_user(db, workspace.id, "manager", "Kirill")
    await _create_task(db, workspace, manager, assignee_user_id=manager.id)

    rows = (
        await db.execute(
            select(Notification).where(Notification.user_id == manager.id)
        )
    ).scalars().all()
    assert rows == []


@skip_no_pg
@pytest.mark.asyncio
async def test_handing_a_task_over_notifies_the_new_assignee(db, workspace):
    from sqlalchemy import select

    from app.activity import services
    from app.notifications.models import Notification

    head = await _make_user(db, workspace.id, "head", "Head")
    first = await _make_user(db, workspace.id, "manager", "First")
    second = await _make_user(db, workspace.id, "manager", "Second")

    task = await _create_task(db, workspace, head, assignee_user_id=first.id)
    await services.update_task_by_id(
        db, workspace.id, task.id, head,
        text=None, task_due_at=None, assignee_user_id=second.id,
    )

    assert task.assignee_user_id == second.id
    rows = (
        await db.execute(
            select(Notification).where(
                Notification.user_id == second.id,
                Notification.kind == "task_assigned",
            )
        )
    ).scalars().all()
    assert len(rows) == 1
    assert await _my_tasks(db, workspace, first) == []
    assert len(await _my_tasks(db, workspace, second)) == 1


@skip_no_pg
@pytest.mark.asyncio
async def test_a_task_from_another_workspace_reads_as_missing(db, workspace):
    from app.activity import services
    from app.auth.models import Workspace

    other_ws = Workspace(name="Other WS", plan="free")
    db.add(other_ws)
    await db.flush()
    outsider = await _make_user(db, other_ws.id, "head", "Outsider")
    task = await _create_task(db, other_ws, outsider)

    head = await _make_user(db, workspace.id, "head", "Head")
    with pytest.raises(services.ActivityNotFound):
        await services.load_task_for_actor(db, workspace.id, task.id, head)


@skip_no_pg
@pytest.mark.asyncio
async def test_blank_text_is_rejected_on_update(db, workspace):
    """Пробелы — не текст задачи. Иначе список пестрит пустыми строками."""
    from app.activity import services

    head = await _make_user(db, workspace.id, "head", "Head")
    task = await _create_task(db, workspace, head, assignee_user_id=head.id)

    with pytest.raises(ValueError):
        await services.update_task_by_id(
            db, workspace.id, task.id, head,
            text="   ", task_due_at=None, assignee_user_id=None,
        )


@skip_no_pg
@pytest.mark.asyncio
async def test_a_task_on_a_trashed_lead_is_not_created(db, workspace):
    """Задачу на удалённый лид не заводим — _get_lead_or_raise отдаёт
    лид даже с deleted_at, но create_task обязан это перепроверить."""
    from app.activity import services
    from app.leads import repositories as leads_repo
    from app.leads.services import LeadNotFound

    head = await _make_user(db, workspace.id, "head", "Head")
    manager = await _make_user(db, workspace.id, "manager", "Kirill")
    lead = await _make_lead(db, workspace.id, assigned_to=manager.id)
    await leads_repo.soft_delete_lead(db, lead, head.id)
    await db.flush()

    with pytest.raises(LeadNotFound):
        await services.create_task(
            db, workspace.id, head,
            text="Задача", task_due_at=TOMORROW,
            assignee_user_id=manager.id, lead_id=lead.id,
        )
