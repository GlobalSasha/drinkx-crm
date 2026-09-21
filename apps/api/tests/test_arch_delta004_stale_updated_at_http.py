"""ARCH-DELTA-004: пять эндпоинтов отвечали 500 уже после того, как сохранили.

Механизм тот же, что в UX-DELTA-003: объект меняют через атрибуты, на flush
`updated_at` (`onupdate=func.now()`) протухает, а сериализация ответа пытается
дочитать его вне транзакции — `MissingGreenlet`. Пользователь видит ошибку,
хотя изменение уже в базе.

Через `ASGITransport` необработанное исключение эндпоинта не превращается в
тело с кодом 500, а всплывает как исключение — поэтому падение теста выглядит
как сам `MissingGreenlet`. Проверяется не только отсутствие исключения, но и
ответ (`updated_at` не пуст) и строка в базе после перечитывания.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

import app.main  # noqa: F401  — настраивает мапперы SQLAlchemy
from tests.conftest import POSTGRES_AVAILABLE

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires PostgreSQL")


async def _user(db, workspace_id, role: str, name: str):
    from app.auth.models import User

    user = User(
        workspace_id=workspace_id,
        email=f"{name}-{uuid.uuid4().hex[:6]}@example.com",
        name=name,
        role=role,
    )
    db.add(user)
    await db.flush()
    return user


async def call(db, actor, method: str, path: str, json=None):
    """Настоящий HTTP-запрос: подменяются только сессия и пользователь."""
    from app.auth.dependencies import current_user
    from app.db import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[current_user] = lambda: actor
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.request(method, path, json=json)
            return res.status_code, res.json()
    finally:
        app.dependency_overrides.clear()


async def _reread(db, model, obj_id):
    """Перечитать строку из базы, а не отдать объект из памяти сессии."""
    db.expire_all()
    return await db.get(model, obj_id)


@skip_no_pg
@pytest.mark.asyncio
async def test_patch_company_returns_200_and_persists(db, workspace):
    from app.companies.models import Company

    head = await _user(db, workspace.id, "head", "head")
    company = Company(workspace_id=workspace.id, name="Ромашка", normalized_name="ромашка")
    db.add(company)
    await db.flush()
    company_id = company.id

    status, body = await call(db, head, "PATCH", f"/companies/{company_id}", {"city": "Казань"})

    assert status == 200, body
    assert body["city"] == "Казань", body
    assert body["updated_at"] is not None, body

    stored = await _reread(db, Company, company_id)
    assert stored.city == "Казань"
    assert stored.updated_at is not None


@skip_no_pg
@pytest.mark.asyncio
async def test_merge_companies_returns_200_and_moves_inn(db, workspace):
    from app.companies.models import Company

    head = await _user(db, workspace.id, "head", "head")
    source = Company(
        workspace_id=workspace.id, name="Ист", normalized_name="ист", inn="7701234567"
    )
    target = Company(workspace_id=workspace.id, name="Цель", normalized_name="цель")
    db.add_all([source, target])
    await db.flush()
    source_id, target_id = source.id, target.id

    status, body = await call(
        db, head, "POST", f"/companies/{source_id}/merge-into/{target_id}"
    )

    assert status == 200, body
    assert body["id"] == str(target_id), body
    assert body["inn"] == "7701234567", body
    assert body["updated_at"] is not None, body

    stored = await _reread(db, Company, target_id)
    assert stored.inn == "7701234567"
    assert stored.updated_at is not None


async def _lead_with_task(db, workspace, owner):
    from app.activity.models import Activity, ActivityType
    from app.leads import repositories as lead_repo

    lead = await lead_repo.create_lead(
        db,
        workspace.id,
        {"company_name": f"Компания {uuid.uuid4().hex[:5]}"},
        assigned_to=owner.id,
        assignment_status="assigned",
    )
    task = Activity(
        workspace_id=None,
        lead_id=lead.id,
        user_id=owner.id,
        type=ActivityType.task.value,
        payload_json={"title": "Задача"},
        body="Задача",
        task_done=False,
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)
    return lead, task


@skip_no_pg
@pytest.mark.asyncio
async def test_archive_task_returns_200_and_persists(db, workspace):
    from app.activity.models import Activity

    owner = await _user(db, workspace.id, "manager", "owner")
    lead, task = await _lead_with_task(db, workspace, owner)
    task_id = task.id

    status, body = await call(db, owner, "DELETE", f"/leads/{lead.id}/activities/{task_id}")

    assert status == 200, body
    assert body["archived_at"] is not None, body
    assert body["updated_at"] is not None, body

    stored = await _reread(db, Activity, task_id)
    assert stored.archived_at is not None
    assert stored.updated_at is not None


@skip_no_pg
@pytest.mark.asyncio
async def test_restore_task_returns_200_and_persists(db, workspace):
    from app.activity.models import Activity

    owner = await _user(db, workspace.id, "manager", "owner")
    lead, task = await _lead_with_task(db, workspace, owner)
    task.archived_at = datetime.now(timezone.utc)
    await db.flush()
    task_id = task.id

    status, body = await call(
        db, owner, "POST", f"/leads/{lead.id}/activities/{task_id}/restore"
    )

    assert status == 200, body
    assert body["archived_at"] is None, body
    assert body["updated_at"] is not None, body

    stored = await _reread(db, Activity, task_id)
    assert stored.archived_at is None
    assert stored.updated_at is not None


@skip_no_pg
@pytest.mark.asyncio
async def test_patch_automation_returns_200_and_persists(db, workspace):
    from app.automation_builder import repositories as automation_repo
    from app.automation_builder.models import Automation

    head = await _user(db, workspace.id, "head", "head")
    automation = await automation_repo.create(
        db,
        workspace_id=workspace.id,
        created_by=head.id,
        name="Было",
        trigger="stage_change",
        trigger_config_json=None,
        condition_json=None,
        action_type="create_task",
        action_config_json={"title": "x"},
        is_active=True,
    )
    await db.flush()
    automation_id = automation.id

    status, body = await call(
        db, head, "PATCH", f"/automations/{automation_id}", {"name": "Стало"}
    )

    assert status == 200, body
    assert body["name"] == "Стало", body
    assert body["updated_at"] is not None, body

    stored = await _reread(db, Automation, automation_id)
    assert stored.name == "Стало"
    assert stored.updated_at is not None


@skip_no_pg
@pytest.mark.asyncio
async def test_patch_contact_stays_green(db, workspace):
    """Контроль: contacts перечитывал объект и до правки — 200 должен остаться."""
    from app.contacts import repositories as contact_repo
    from app.contacts.models import Contact
    from app.leads import repositories as lead_repo

    owner = await _user(db, workspace.id, "manager", "owner")
    lead = await lead_repo.create_lead(
        db,
        workspace.id,
        {"company_name": "Контроль"},
        assigned_to=owner.id,
        assignment_status="assigned",
    )
    contact = await contact_repo.create(db, lead.id, {"name": "Иван", "workspace_id": workspace.id})
    contact_id = contact.id

    status, body = await call(
        db, owner, "PATCH", f"/leads/{lead.id}/contacts/{contact_id}", {"name": "Пётр"}
    )

    assert status == 200, body
    stored = await _reread(db, Contact, contact_id)
    assert stored.name == "Пётр"


# --- вторая волна: те же грабли, найдены на независимом ревью ----------------


@skip_no_pg
@pytest.mark.asyncio
async def test_patch_template_returns_200_and_persists(db, workspace):
    from app.template.models import MessageTemplate

    admin = await _user(db, workspace.id, "admin", "admin")
    template = MessageTemplate(
        workspace_id=workspace.id, name="Шаблон", channel="email", text="было", created_by=admin.id
    )
    db.add(template)
    await db.flush()
    template_id = template.id

    status, body = await call(db, admin, "PATCH", f"/templates/{template_id}", {"text": "стало"})

    assert status == 200, body
    assert body["text"] == "стало", body
    assert body["updated_at"] is not None, body

    stored = await _reread(db, MessageTemplate, template_id)
    assert stored.text == "стало"


@skip_no_pg
@pytest.mark.asyncio
async def test_restore_lead_returns_200_and_persists(db, workspace):
    from app.leads import repositories as lead_repo
    from app.leads.models import Lead

    head = await _user(db, workspace.id, "head", "head")
    lead = await lead_repo.create_lead(
        db,
        workspace.id,
        {"company_name": "Из корзины"},
        assigned_to=head.id,
        assignment_status="assigned",
    )
    await lead_repo.soft_delete_lead(db, lead, head.id)
    lead_id = lead.id

    status, body = await call(db, head, "POST", f"/leads/{lead_id}/restore")

    assert status == 200, body
    assert body["updated_at"] is not None, body

    stored = await _reread(db, Lead, lead_id)
    assert stored.deleted_at is None
    assert stored.deleted_by is None


@skip_no_pg
@pytest.mark.asyncio
async def test_move_stage_returns_200_and_persists(db, workspace, pipeline):
    from app.leads import repositories as lead_repo
    from app.leads.models import Lead
    from app.pipelines.models import Stage

    pipe, first_stage = pipeline
    second_stage = Stage(
        pipeline_id=pipe.id, name="Контакт", position=2, color="#aabbcc", rot_days=14
    )
    db.add(second_stage)
    await db.flush()
    # id забираем заранее: `_reread` делает `expire_all()`, после которого
    # обращение к атрибуту любого другого объекта сессии ушло бы в ленивую
    # догрузку — вне транзакции это тот же MissingGreenlet, только в тесте.
    second_stage_id = second_stage.id
    head = await _user(db, workspace.id, "head", "head")
    lead = await lead_repo.create_lead(
        db,
        workspace.id,
        {"company_name": "Переезд", "pipeline_id": pipe.id, "stage_id": first_stage.id},
        assigned_to=head.id,
        assignment_status="assigned",
    )
    lead_id = lead.id

    status, body = await call(
        db, head, "POST", f"/leads/{lead_id}/move-stage", {"stage_id": str(second_stage_id)}
    )

    assert status == 200, body
    assert body["stage_id"] == str(second_stage_id), body
    assert body["updated_at"] is not None, body

    stored = await _reread(db, Lead, lead_id)
    assert stored.stage_id == second_stage_id


# --- третья волна: объединение дублей (проверка ChatGPT по snapshot) ---------


@skip_no_pg
@pytest.mark.asyncio
async def test_merge_leads_returns_200_and_persists(db, workspace):
    """`POST /leads/{id}/merge` отдавал 500 после того, как объединил.

    Мастер меняется через атрибуты (пустые поля заполняются из дубля), затем
    flush — и `updated_at` протухает ровно так же, как в остальных местах
    ARCH-DELTA-004.
    """
    from app.leads.models import Lead

    head = await _user(db, workspace.id, "head", "head")
    master = Lead(
        workspace_id=workspace.id,
        company_name="Ромашка",
        assignment_status="pool",
        tags_json=["a"],
    )
    duplicate = Lead(
        workspace_id=workspace.id,
        company_name="Ромашка Дубль",
        email="ivan@romashka.ru",
        phone="89161234567",
        city="Казань",
        assignment_status="pool",
        tags_json=["b"],
    )
    db.add_all([master, duplicate])
    await db.flush()
    master_id, duplicate_id = master.id, duplicate.id

    status, body = await call(
        db,
        head,
        "POST",
        f"/leads/{master_id}/merge",
        {"duplicate_ids": [str(duplicate_id)]},
    )

    assert status == 200, body
    assert body["id"] == str(master_id), body
    assert body["updated_at"] is not None, body
    # Мастер действительно забрал пустые поля дубля, а не просто «не упал».
    assert body["email"] == "ivan@romashka.ru", body
    assert body["city"] == "Казань", body

    stored_master = await _reread(db, Lead, master_id)
    assert stored_master.email == "ivan@romashka.ru"
    assert stored_master.city == "Казань"
    assert sorted(stored_master.tags_json) == ["a", "b"]
    assert stored_master.updated_at is not None

    stored_duplicate = await _reread(db, Lead, duplicate_id)
    assert stored_duplicate.archived_at is not None
    assert stored_duplicate.merged_into_id == master_id
