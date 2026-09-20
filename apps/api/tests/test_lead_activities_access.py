"""Кто может читать и править ленту лида — `/leads/{lead_id}/activities`.

Тот же разрыв, что нашёлся у задач лида: роутер подключён отдельно от
`/leads`, поэтому страж карточки на него не распространялся. Обработчики
сверяют только рабочее пространство, так что менеджер, знающий UUID, читал
ленту чужого лида, заводил в ней записи, закрывал и удалял чужие задачи.

Проверки идут через HTTP: правило живёт в зависимости роутера, и тест,
зовущий обработчик напрямую, прошёл бы на сломанном коде.

Права внутри ленты (автор или админ правит запись) этим стражем не
заменяются — он отвечает только на вопрос «пускать ли к этому лиду вообще».
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
SECRET = "Секретная запись"


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


async def _task(db, lead_id, author_id, text: str = SECRET):
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


async def _call(db, actor, method: str, path: str, **kwargs):
    """Настоящий HTTP-запрос от имени `actor`.

    Подменяются только границы — сессия базы и текущий пользователь.
    Зависимости роутеров работают как в проде: их и проверяем.
    """
    from app.auth.dependencies import current_user
    from app.db import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[current_user] = lambda: actor
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, **kwargs)
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Чтение
# ---------------------------------------------------------------------------


@skip_no_pg
@pytest.mark.asyncio
async def test_a_manager_reads_the_feed_of_their_own_lead(db, workspace):
    owner = await _user(db, workspace.id, "manager", "Owner")
    lead = await _lead(db, workspace.id, owner.id)
    await _task(db, lead.id, owner.id, "Своя запись")

    res = await _call(db, owner, "GET", f"/leads/{lead.id}/activities")
    assert res.status_code == 200
    assert [i["body"] for i in res.json()["items"]] == ["Своя запись"]


@skip_no_pg
@pytest.mark.asyncio
async def test_a_manager_gets_404_on_a_colleagues_feed(db, workspace):
    owner = await _user(db, workspace.id, "manager", "Owner")
    stranger = await _user(db, workspace.id, "manager", "Stranger")
    lead = await _lead(db, workspace.id, owner.id)
    await _task(db, lead.id, owner.id)

    res = await _call(db, stranger, "GET", f"/leads/{lead.id}/activities")
    assert res.status_code == 404
    assert res.json()["detail"] == "Lead not found"
    assert SECRET not in res.text


@skip_no_pg
@pytest.mark.asyncio
async def test_the_archive_of_a_colleagues_lead_is_closed_too(db, workspace):
    """Отдельный маршрут под тем же префиксом — страж роутера закрывает и его,
    и всё, что допишут туда потом."""
    owner = await _user(db, workspace.id, "manager", "Owner")
    stranger = await _user(db, workspace.id, "manager", "Stranger")
    lead = await _lead(db, workspace.id, owner.id)

    res = await _call(db, stranger, "GET", f"/leads/{lead.id}/activities/archive")
    assert res.status_code == 404


@skip_no_pg
@pytest.mark.asyncio
async def test_the_head_and_the_admin_read_a_managers_feed(db, workspace):
    owner = await _user(db, workspace.id, "manager", "Owner")
    head = await _user(db, workspace.id, "head", "Head")
    admin = await _user(db, workspace.id, "admin", "Admin")
    lead = await _lead(db, workspace.id, owner.id)
    await _task(db, lead.id, owner.id, "Запись менеджера")

    for actor in (head, admin):
        res = await _call(db, actor, "GET", f"/leads/{lead.id}/activities")
        assert res.status_code == 200, actor.role
        assert [i["body"] for i in res.json()["items"]] == ["Запись менеджера"]


@skip_no_pg
@pytest.mark.asyncio
async def test_another_workspace_gets_404_even_for_an_admin(db, workspace):
    from app.auth.models import Workspace

    owner = await _user(db, workspace.id, "manager", "Owner")
    lead = await _lead(db, workspace.id, owner.id)
    await _task(db, lead.id, owner.id)

    other_ws = Workspace(name="Other WS", plan="free")
    db.add(other_ws)
    await db.flush()
    outsider = await _user(db, other_ws.id, "admin", "Outsider")

    res = await _call(db, outsider, "GET", f"/leads/{lead.id}/activities")
    assert res.status_code == 404
    assert SECRET not in res.text


# ---------------------------------------------------------------------------
# Запись. Чтение было бы полбеды: по этим же маршрутам чужую ленту можно
# пополнять и чужие задачи закрывать.
# ---------------------------------------------------------------------------


@skip_no_pg
@pytest.mark.asyncio
async def test_a_manager_cannot_write_into_a_colleagues_feed(db, workspace):
    owner = await _user(db, workspace.id, "manager", "Owner")
    stranger = await _user(db, workspace.id, "manager", "Stranger")
    lead = await _lead(db, workspace.id, owner.id)
    task = await _task(db, lead.id, owner.id)

    base = f"/leads/{lead.id}/activities"
    attempts = [
        ("POST", base, {"json": {"type": "note", "body": "Я тут был"}}),
        ("POST", f"{base}/{task.id}/complete-task", {}),
        ("POST", f"{base}/{task.id}/reopen-task", {}),
        ("PATCH", f"{base}/{task.id}", {"json": {"body": "Переписал"}}),
        ("PATCH", f"{base}/{task.id}/comment", {"json": {"body": "Переписал"}}),
        ("DELETE", f"{base}/{task.id}", {}),
        ("POST", f"{base}/{task.id}/restore", {}),
    ]
    for method, path, kwargs in attempts:
        res = await _call(db, stranger, method, path, **kwargs)
        assert res.status_code == 404, f"{method} {path} -> {res.status_code}"

    # И запись действительно осталась нетронутой.
    await db.refresh(task)
    assert task.body == SECRET
    assert task.task_done is False
    assert task.archived_at is None


@skip_no_pg
@pytest.mark.asyncio
async def test_the_owner_still_closes_their_own_task(db, workspace):
    """Страж не должен мешать обычной работе."""
    owner = await _user(db, workspace.id, "manager", "Owner")
    lead = await _lead(db, workspace.id, owner.id)
    task = await _task(db, lead.id, owner.id, "Позвонить")

    res = await _call(
        db, owner, "POST", f"/leads/{lead.id}/activities/{task.id}/complete-task"
    )
    assert res.status_code == 200
    assert res.json()["task_done"] is True


@skip_no_pg
@pytest.mark.asyncio
async def test_a_missing_lead_answers_the_same_as_a_foreign_one(db, workspace):
    """Иначе по коду ответа можно перебирать чужие UUID."""
    owner = await _user(db, workspace.id, "manager", "Owner")
    stranger = await _user(db, workspace.id, "manager", "Stranger")
    foreign = await _lead(db, workspace.id, owner.id)

    missing_res = await _call(db, stranger, "GET", f"/leads/{uuid.uuid4()}/activities")
    foreign_res = await _call(db, stranger, "GET", f"/leads/{foreign.id}/activities")

    assert missing_res.status_code == foreign_res.status_code == 404
    assert missing_res.json() == foreign_res.json()
