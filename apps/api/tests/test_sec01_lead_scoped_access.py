"""SEC-01: доступ к лиду и его дочерним записям.

Правило одно на всё приложение: менеджер работает только с закреплённым за
ним лидом, руководитель и админ — с любым в своём пространстве, чужой и
несуществующий лид отвечают одинаково (404). До правки восемь роутеров
подключались отдельно от `/leads` и про это правило не знали: менеджер,
знающий UUID, читал ЛПР, ленту, переписку, заметки, обогащение,
AI-рекомендацию и коммерческие предложения чужого лида — и часть из этого
менял.

Проверки идут через HTTP: правило живёт в зависимостях роутера, и вызов
обработчика напрямую его не задевает.

Разведка, с которой всё началось: `recon_sec01_lead_scoped.py`,
`recon_sec01_child_ids.py`.
"""
from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

import app.main  # noqa: F401  — настраивает мапперы SQLAlchemy
from tests.conftest import POSTGRES_AVAILABLE

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires PostgreSQL")


# --- обвязка ---------------------------------------------------------------

async def _user(db, workspace_id, role, name):
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


async def _lead(db, workspace_id, owner_id, name="Компания"):
    from app.leads import repositories as repo

    return await repo.create_lead(
        db, workspace_id, dict(company_name=name),
        assigned_to=owner_id, assignment_status="assigned",
    )


async def call(db, actor, method, path, body=None):
    from app.auth.dependencies import current_user
    from app.db import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[current_user] = lambda: actor
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            kwargs = {"json": body} if method in ("POST", "PATCH", "PUT") else {}
            if method in ("POST", "PATCH", "PUT") and body is None:
                kwargs = {"json": {}}
            return await c.request(method, path, **kwargs)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
async def scene(db, workspace):
    """Владелец, посторонний менеджер, руководитель, админ и чужой лид
    с полным набором дочерних записей."""
    from app.activity.models import Activity, ActivityType
    from app.contacts.models import Contact
    from app.followups.models import Followup
    from app.notes.models import LeadNote
    from app.quote.models import Quote

    owner = await _user(db, workspace.id, "manager", "Owner")
    stranger = await _user(db, workspace.id, "manager", "Stranger")
    head = await _user(db, workspace.id, "head", "Head")
    admin = await _user(db, workspace.id, "admin", "Admin")
    lead = await _lead(db, workspace.id, owner.id, "Компания владельца")

    contact = Contact(workspace_id=workspace.id, lead_id=lead.id, name="ЛПР владельца")
    note = LeadNote(
        workspace_id=workspace.id, lead_id=lead.id, user_id=owner.id,
        text="Заметка владельца",
    )
    followup = Followup(
        lead_id=lead.id, name="Касание владельца", reminder_kind="manager",
        status="pending",
    )
    task = Activity(
        workspace_id=None, lead_id=lead.id, user_id=owner.id,
        type=ActivityType.task.value, payload_json={"title": "Задача владельца"},
        body="Задача владельца", task_done=False,
    )
    file_act = Activity(
        workspace_id=None, lead_id=lead.id, user_id=owner.id,
        type=ActivityType.file.value,
        payload_json={"parent_task_id": None, "filename": "секрет.pdf"},
        body="секрет.pdf", file_url="s3://bucket/секрет.pdf",
    )
    quote = Quote(
        workspace_id=workspace.id, lead_id=lead.id, created_by=owner.id,
        number="КП-001", status="draft", subtotal=1000, total=1200,
    )
    for row in (contact, note, followup, task, file_act, quote):
        db.add(row)
    await db.flush()
    file_act.payload_json = {"parent_task_id": str(task.id), "filename": "секрет.pdf"}
    await db.flush()

    return {
        "owner": owner, "stranger": stranger, "head": head, "admin": admin,
        "lead": lead, "contact": contact, "note": note, "followup": followup,
        "task": task, "file": file_act, "quote": quote, "workspace": workspace,
    }


# Чтение по каждому домену: путь и то, что в ответе быть не должно.
READS = [
    ("/leads/{lead}/contacts", "ЛПР владельца"),
    ("/leads/{lead}/notes", "Заметка владельца"),
    ("/leads/{lead}/followups", "Касание владельца"),
    ("/leads/{lead}/feed", "Задача владельца"),
    ("/leads/{lead}/inbox", None),
    ("/leads/{lead}/enrichment", None),
    ("/leads/{lead}/enrichment/latest", None),
    ("/leads/{lead}/agent/suggestion", None),
    ("/api/leads/{lead}/quotes", "КП-001"),
    ("/leads/{lead}/tasks/{task}/files", "секрет.pdf"),
]


def _fill(path, s):
    return path.replace("{lead}", str(s["lead"].id)).replace("{task}", str(s["task"].id))


@skip_no_pg
@pytest.mark.asyncio
async def test_the_owner_still_reads_everything(db, scene):
    for path, _needle in READS:
        res = await call(db, scene["owner"], "GET", _fill(path, scene))
        assert res.status_code == 200, (path, res.text[:200])


@skip_no_pg
@pytest.mark.asyncio
async def test_a_colleague_reads_nothing_of_a_foreign_lead(db, scene):
    for path, needle in READS:
        res = await call(db, scene["stranger"], "GET", _fill(path, scene))
        assert res.status_code == 404, (path, res.status_code)
        if needle:
            assert needle not in res.text, path


@skip_no_pg
@pytest.mark.asyncio
async def test_the_head_and_the_admin_read_a_managers_lead(db, scene):
    for role in ("head", "admin"):
        for path, _needle in READS:
            res = await call(db, scene[role], "GET", _fill(path, scene))
            assert res.status_code == 200, (role, path, res.text[:200])


@skip_no_pg
@pytest.mark.asyncio
async def test_another_workspace_sees_nothing(db, scene, workspace):
    from app.auth.models import Workspace

    other = Workspace(name="Other WS", plan="free")
    db.add(other)
    await db.flush()
    outsider = await _user(db, other.id, "admin", "Outsider")

    for path, needle in READS:
        res = await call(db, outsider, "GET", _fill(path, scene))
        assert res.status_code == 404, path
        if needle:
            assert needle not in res.text, path


# --- запись ---------------------------------------------------------------


@skip_no_pg
@pytest.mark.asyncio
async def test_a_colleague_cannot_write_to_a_foreign_lead(db, scene):
    """И отказ должен быть до обработчика: ничего не изменилось."""
    s = scene
    L, C, N, F, Q = (
        str(s["lead"].id), str(s["contact"].id), str(s["note"].id),
        str(s["followup"].id), str(s["quote"].id),
    )
    attempts = [
        ("POST", f"/leads/{L}/contacts", {"name": "Подставной"}),
        ("PATCH", f"/leads/{L}/contacts/{C}", {"name": "Перехват"}),
        ("DELETE", f"/leads/{L}/contacts/{C}", None),
        ("POST", f"/leads/{L}/notes", {"text": "Я тут был"}),
        ("PATCH", f"/leads/{L}/notes/{N}", {"text": "Перехват"}),
        ("DELETE", f"/leads/{L}/notes/{N}", None),
        ("POST", f"/leads/{L}/followups", {"name": "Чужое касание"}),
        ("PATCH", f"/leads/{L}/followups/{F}", {"name": "Перехват"}),
        ("DELETE", f"/leads/{L}/followups/{F}", None),
        ("POST", f"/leads/{L}/followups/{F}/complete", None),
        ("POST", f"/api/leads/{L}/quotes", {"items": []}),
        ("PATCH", f"/api/quotes/{Q}", {"status": "sent"}),
        ("POST", f"/api/quotes/{Q}/status", {"status": "sent"}),
        ("POST", f"/api/quotes/{Q}/apply-to-deal", None),
        ("DELETE", f"/api/quotes/{Q}", None),
        ("POST", f"/leads/{L}/feed/ask-blake", {"question": "что тут?"}),
        ("POST", f"/leads/{L}/agent/chat", {"message": "привет"}),
        ("POST", f"/leads/{L}/agent/suggestion/refresh", None),
        ("POST", f"/leads/{L}/enrichment", {}),
        ("POST", f"/leads/{L}/inbox/send", {"subject": "тема", "body": "текст"}),
    ]
    for method, path, body in attempts:
        res = await call(db, scene["stranger"], method, path, body)
        assert res.status_code == 404, (method, path, res.status_code, res.text[:150])

    # Последствий нет: записи владельца на месте, ничего не создано.
    for row, field, value in (
        (s["contact"], "name", "ЛПР владельца"),
        (s["note"], "text", "Заметка владельца"),
        (s["followup"], "name", "Касание владельца"),
        (s["quote"], "status", "draft"),
    ):
        await db.refresh(row)
        assert getattr(row, field) == value, (row, field)
    assert s["followup"].status == "pending"

    from sqlalchemy import func, select

    from app.contacts.models import Contact
    from app.notes.models import LeadNote
    from app.quote.models import Quote

    for model in (Contact, LeadNote, Quote):
        count = (
            await db.execute(
                select(func.count()).select_from(model).where(model.lead_id == s["lead"].id)
            )
        ).scalar_one()
        assert count == 1, model


@skip_no_pg
@pytest.mark.asyncio
async def test_the_owner_can_still_write(db, scene):
    """Страж не должен мешать обычной работе."""
    s = scene
    L = str(s["lead"].id)
    created = await call(db, s["owner"], "POST", f"/leads/{L}/notes", {"text": "Моя заметка"})
    assert created.status_code == 201, created.text[:200]
    done = await call(
        db, s["owner"], "POST", f"/leads/{L}/followups/{s['followup'].id}/complete"
    )
    assert done.status_code == 200, done.text[:200]


# --- дочерние записи: свой лид, чужой объект -------------------------------


@skip_no_pg
@pytest.mark.asyncio
async def test_own_lead_with_a_foreign_child_id_is_refused(db, scene, workspace):
    """Подставить свой lead_id и чужой contact_id не должно помогать."""
    s = scene
    peer = await _user(db, workspace.id, "manager", "Peer")
    my_lead = await _lead(db, workspace.id, peer.id, "Лид коллеги")
    M = str(my_lead.id)

    cases = [
        ("PATCH", f"/leads/{M}/contacts/{s['contact'].id}", {"name": "Перехват"}),
        ("DELETE", f"/leads/{M}/contacts/{s['contact'].id}", None),
        ("PATCH", f"/leads/{M}/notes/{s['note'].id}", {"text": "Перехват"}),
        ("DELETE", f"/leads/{M}/notes/{s['note'].id}", None),
        ("PATCH", f"/leads/{M}/followups/{s['followup'].id}", {"name": "Перехват"}),
        ("DELETE", f"/leads/{M}/followups/{s['followup'].id}", None),
        ("POST", f"/leads/{M}/followups/{s['followup'].id}/complete", None),
        ("PATCH", f"/leads/{M}/activities/{s['task'].id}", {"body": "Перехват"}),
        ("POST", f"/leads/{M}/activities/{s['task'].id}/complete-task", None),
        ("DELETE", f"/leads/{M}/activities/{s['task'].id}", None),
    ]
    for method, path, body in cases:
        res = await call(db, peer, method, path, body)
        assert res.status_code == 404, (method, path, res.status_code)

    # Список файлов по чужой задаче под своим лидом отвечает 200, но пустым:
    # выборка сужена по lead_id внутри запроса. Проверяем именно это, а не
    # код ответа — 200 сам по себе здесь ничего не нарушает.
    files = await call(db, peer, "GET", f"/leads/{M}/tasks/{s['task'].id}/files")
    assert files.status_code == 200
    assert files.json() == []
    assert "секрет.pdf" not in files.text

    await db.refresh(s["contact"])
    await db.refresh(s["note"])
    assert s["contact"].name == "ЛПР владельца"
    assert s["note"].text == "Заметка владельца"


# --- SEC-01-J: файлы по activity_id ---------------------------------------


@skip_no_pg
@pytest.mark.asyncio
async def test_file_download_and_delete_check_the_lead_not_just_the_workspace(db, scene, monkeypatch):
    """Ни ссылки, ни удаления: отказ наступает до обращения к хранилищу."""
    from app.activity import files as files_svc

    calls: list[str] = []

    async def _no_url(activity):
        calls.append("signed_url")
        return "https://example.invalid/secret"

    async def _no_delete(db_, activity):
        calls.append("delete")

    monkeypatch.setattr(files_svc, "signed_download_url", _no_url)
    monkeypatch.setattr(files_svc, "delete_file_activity", _no_delete)

    A = str(scene["file"].id)
    got = await call(db, scene["stranger"], "GET", f"/activities/{A}/download")
    assert got.status_code == 404
    assert "example.invalid" not in got.text
    removed = await call(db, scene["stranger"], "DELETE", f"/activities/{A}/file")
    assert removed.status_code == 404
    assert calls == [], f"хранилище не должно было вызываться: {calls}"

    # Владельцу — работает, и файл на месте.
    ok = await call(db, scene["owner"], "GET", f"/activities/{A}/download")
    assert ok.status_code == 200
    assert calls == ["signed_url"]

    from sqlalchemy import select

    from app.activity.models import Activity

    still = (
        await db.execute(select(Activity.id).where(Activity.id == scene["file"].id))
    ).scalar_one_or_none()
    assert still is not None


# --- инвентаризация --------------------------------------------------------


@skip_no_pg
@pytest.mark.asyncio
async def test_every_lead_scoped_route_is_guarded(db, scene):
    """Новый роутер с `{lead_id}` обязан получить общий страж.

    Это не «проверка наличия зависимости вместо поведения»: поведение
    закреплено тестами выше. Здесь ловится другое — что следующий домен
    подключит свой роутер и снова забудет про правило. Исключения
    перечисляются явно, с причиной.
    """
    from fastapi.routing import APIRoute

    from app.main import app

    # `/external/v1` живёт на ключе интеграции, а не на пользователе:
    # `current_user` там не резолвится, и этот страж к нему неприменим.
    # Его доступ проверяется своей политикой (SEC-03 в бэклоге).
    ALLOWED_WITHOUT_GUARD = {"/external/v1/leads/{lead_id}", "/external/v1/leads/{lead_id}/summary"}

    def names(route):
        out = []

        def walk(d):
            n = getattr(d.call, "__name__", None)
            if n:
                out.append(n)
            for s in d.dependencies:
                walk(s)

        walk(route.dependant)
        return out

    unguarded = sorted(
        {
            r.path
            for r in app.routes
            if isinstance(r, APIRoute)
            and "{lead_id}" in r.path
            and r.path not in ALLOWED_WITHOUT_GUARD
            and "lead_access_guard" not in names(r)
        }
    )
    assert unguarded == [], (
        "маршруты с {lead_id} без общей проверки доступа: " + ", ".join(unguarded)
    )
