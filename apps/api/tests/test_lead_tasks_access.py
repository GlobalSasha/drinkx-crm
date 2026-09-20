"""Кто может прочитать GET /leads/{lead_id}/tasks (аудит G5, ревью доступа).

Эндпоинт появился в G5 и был подключён отдельным роутером. Страж, который
закрывает `/leads/{id}`, на него не распространялся, а
`services._get_lead_or_raise` сверяет только рабочее пространство. Менеджер,
знающий UUID чужого лида, получал по нему задачи — и строки, и счётчики.

Проверки идут через HTTP, а не вызовом функции обработчика: дыра была ровно в
том, что правило живёт в зависимости роутера. Тест, зовущий обработчик
напрямую, прошёл бы и на сломанном коде.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

import app.main  # noqa: F401  — настраивает мапперы SQLAlchemy
from tests.conftest import POSTGRES_AVAILABLE

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires PostgreSQL")

NOW = datetime.now(timezone.utc)


async def _user(db, workspace_id, role: str, name: str):
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


async def _lead(db, workspace_id, owner_id):
    from app.leads import repositories as repo

    return await repo.create_lead(
        db, workspace_id,
        dict(company_name=f"Company {uuid.uuid4().hex[:6]}"),
        assigned_to=owner_id,
        assignment_status="assigned",
    )


async def _task(db, workspace_id, lead_id, author_id, text: str):
    from app.activity.models import Activity, ActivityType

    row = Activity(
        workspace_id=None,
        lead_id=lead_id,
        user_id=author_id,
        type=ActivityType.task.value,
        payload_json={"title": text},
        body=text,
        task_due_at=NOW + timedelta(days=1),
        task_done=False,
        created_at=NOW,
    )
    db.add(row)
    await db.flush()
    return row


async def _get(db, actor, lead_id):
    """Настоящий HTTP-запрос к приложению от имени `actor`.

    Подменяются только границы: сессия базы (та же, что у теста, чтобы были
    видны незакоммиченные строки) и текущий пользователь. Стражи роутеров при
    этом работают как в проде — их-то и проверяем.
    """
    from app.auth.dependencies import current_user
    from app.db import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[current_user] = lambda: actor
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get(f"/leads/{lead_id}/tasks")
    finally:
        app.dependency_overrides.clear()


@skip_no_pg
@pytest.mark.asyncio
async def test_a_manager_reads_the_tasks_of_their_own_lead(db, workspace):
    manager = await _user(db, workspace.id, "manager", "Owner")
    lead = await _lead(db, workspace.id, manager.id)
    await _task(db, workspace.id, lead.id, manager.id, "Позвонить")

    res = await _get(db, manager, lead.id)
    assert res.status_code == 200
    body = res.json()
    assert [i["text"] for i in body["items"]] == ["Позвонить"]
    assert body["counts"]["total"] == 1


@skip_no_pg
@pytest.mark.asyncio
async def test_a_manager_gets_404_on_a_colleagues_lead(db, workspace):
    """Тот же workspace, чужой лид. 404, а не 403: отказ не должен
    подтверждать, что такой лид существует."""
    owner = await _user(db, workspace.id, "manager", "Owner")
    stranger = await _user(db, workspace.id, "manager", "Stranger")
    lead = await _lead(db, workspace.id, owner.id)
    await _task(db, workspace.id, lead.id, owner.id, "Секретная задача")

    res = await _get(db, stranger, lead.id)
    assert res.status_code == 404
    assert res.json()["detail"] == "Lead not found"
    # Ни строк, ни счётчиков: до G5-ревью сюда приезжали и те и другие.
    assert "items" not in res.text and "counts" not in res.text
    assert "Секретная задача" not in res.text


@skip_no_pg
@pytest.mark.asyncio
async def test_the_head_reads_a_managers_lead(db, workspace):
    head = await _user(db, workspace.id, "head", "Head")
    manager = await _user(db, workspace.id, "manager", "Owner")
    lead = await _lead(db, workspace.id, manager.id)
    await _task(db, workspace.id, lead.id, manager.id, "Позвонить")

    res = await _get(db, head, lead.id)
    assert res.status_code == 200
    assert res.json()["counts"]["total"] == 1


@skip_no_pg
@pytest.mark.asyncio
async def test_an_admin_reads_a_managers_lead(db, workspace):
    admin = await _user(db, workspace.id, "admin", "Admin")
    manager = await _user(db, workspace.id, "manager", "Owner")
    lead = await _lead(db, workspace.id, manager.id)
    await _task(db, workspace.id, lead.id, manager.id, "Позвонить")

    res = await _get(db, admin, lead.id)
    assert res.status_code == 200
    assert [i["text"] for i in res.json()["items"]] == ["Позвонить"]


@skip_no_pg
@pytest.mark.asyncio
async def test_another_workspace_gets_404_even_for_an_admin(db, workspace):
    """Роль не переносится через границу пространства."""
    from app.auth.models import Workspace

    owner = await _user(db, workspace.id, "manager", "Owner")
    lead = await _lead(db, workspace.id, owner.id)
    await _task(db, workspace.id, lead.id, owner.id, "Секретная задача")

    other_ws = Workspace(name="Other WS", plan="free")
    db.add(other_ws)
    await db.flush()
    outsider = await _user(db, other_ws.id, "admin", "Outsider")

    res = await _get(db, outsider, lead.id)
    assert res.status_code == 404
    assert "Секретная задача" not in res.text
    assert "counts" not in res.text


@skip_no_pg
@pytest.mark.asyncio
async def test_a_lead_that_does_not_exist_answers_the_same_as_a_foreign_one(db, workspace):
    """Иначе по коду ответа можно перебирать чужие UUID."""
    stranger = await _user(db, workspace.id, "manager", "Stranger")
    owner = await _user(db, workspace.id, "manager", "Owner")
    foreign = await _lead(db, workspace.id, owner.id)

    missing_res = await _get(db, stranger, uuid.uuid4())
    foreign_res = await _get(db, stranger, foreign.id)

    assert missing_res.status_code == foreign_res.status_code == 404
    assert missing_res.json() == foreign_res.json()
