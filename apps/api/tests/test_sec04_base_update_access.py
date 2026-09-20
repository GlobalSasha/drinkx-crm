"""SEC-04 — разведка самостоятельного домена `base_update`.

Путь AI-обновления базы: загрузка .md → извлечение/сопоставление →
предпросмотр → решения по конфликтам → применение в worker. У домена
свои маршруты (`/api/base-update/*`), своя таблица заданий и свой
исполнитель, поэтому исправления `import_export` его не закрывают.

Проверяется:

* кто вообще допущен к маршрутам (роль) и что видит другое пространство;
* подмена дочерних ID — `job_id`, `conflict_id`;
* решение по конфликту, указывающее на чужую компанию, чужой лид и
  чужой контакт, — что worker при этом реально пишет;
* откуда берутся `workspace` и владелец у создаваемых записей.

AI, очередь и хранилище не участвуют: задания собираются прямо в базе,
`celery_app.send_task` подменяется записывающей заглушкой.
"""
from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

import app.main  # noqa: F401 — настраивает мапперы SQLAlchemy
from app.base_update import constants as c
from tests.conftest import POSTGRES_AVAILABLE

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires PostgreSQL")


# --- обвязка ---------------------------------------------------------------

async def _workspace(db, name: str):
    from app.auth.models import Workspace

    ws = Workspace(name=name, plan="pro", sprint_capacity_per_week=20)
    db.add(ws)
    await db.flush()
    return ws


async def _user(db, workspace_id, name: str, role: str):
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


async def _default_pipeline(db, workspace):
    """Воронка по умолчанию + этап с позицией 0 — их ищет `create_new_lead`."""
    from app.pipelines.models import Pipeline, Stage

    p = Pipeline(workspace_id=workspace.id, name="Основная", type="sales", position=0)
    db.add(p)
    await db.flush()
    s = Stage(pipeline_id=p.id, name="Новые", position=0, color="#aabbcc", rot_days=14)
    db.add(s)
    await db.flush()
    workspace.default_pipeline_id = p.id
    await db.flush()
    return p, s


async def _company(db, workspace_id, name: str, **fields):
    from app.companies.models import Company

    co = Company(
        workspace_id=workspace_id, name=name, normalized_name=name.lower(), **fields
    )
    db.add(co)
    await db.flush()
    return co


async def _lead(db, workspace_id, name, owner_id=None, company_id=None):
    from app.leads import repositories as repo

    data = dict(company_name=name)
    if company_id is not None:
        data["company_id"] = company_id
    return await repo.create_lead(
        db, workspace_id, data,
        assigned_to=owner_id,
        assignment_status="assigned" if owner_id else "pool",
    )


async def _contact(db, workspace_id, lead_id, name, **fields):
    from app.contacts.models import Contact

    ct = Contact(workspace_id=workspace_id, lead_id=lead_id, name=name, **fields)
    db.add(ct)
    await db.flush()
    return ct


async def _job(db, workspace_id, user_id, status=c.JOB_READY):
    from app.base_update.models import IngestJob

    job = IngestJob(
        workspace_id=workspace_id,
        user_id=user_id,
        status=status,
        file_count=1,
        source_filenames=["карточка.md"],
        stats_json={},
    )
    db.add(job)
    await db.flush()
    return job


async def _record(db, job, *, name="Компания", match_company_id=None,
                  match_lead_id=None, extracted=None):
    from app.base_update.models import IngestRecord

    rec = IngestRecord(
        ingest_job_id=job.id,
        company_name=name,
        normalized_name=name.lower(),
        extracted_json=extracted or {"company": {"name": name}},
        match_company_id=match_company_id,
        match_lead_id=match_lead_id,
        confidence=0.9,
    )
    db.add(rec)
    await db.flush()
    return rec


async def _conflict(db, job, record, *, type_, target_kind, field_name=None,
                    incoming=None, status=c.CONFLICT_OPEN, resolution=None,
                    resolved_value=None, candidates=None):
    from app.base_update.models import IngestConflict

    cf = IngestConflict(
        ingest_job_id=job.id,
        ingest_record_id=record.id,
        type=type_,
        target_kind=target_kind,
        field_name=field_name,
        base_value=None,
        incoming_value=incoming,
        candidates_json=candidates,
        status=status,
        resolution=resolution,
        resolved_value=resolved_value,
    )
    db.add(cf)
    await db.flush()
    return cf


async def call(db, actor, method, path, body=None, files=None, raise_errors=True):
    from app.auth.dependencies import current_user
    from app.db import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[current_user] = lambda: actor
    try:
        transport = ASGITransport(app=app, raise_app_exceptions=raise_errors)
        async with AsyncClient(transport=transport, base_url="http://test") as cl:
            kwargs: dict = {}
            if files is not None:
                kwargs["files"] = files
            elif method in ("POST", "PATCH", "PUT"):
                kwargs["json"] = body if body is not None else {}
            return await cl.request(method, path, **kwargs)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def no_queue(monkeypatch):
    """Очередь заменяется записывающей заглушкой: ни одного реального вызова."""
    from app.scheduled.celery_app import celery_app

    sent: list[tuple] = []
    monkeypatch.setattr(
        celery_app, "send_task", lambda name, *a, **kw: sent.append((name, a, kw))
    )
    return sent


@pytest.fixture
async def scene(db):
    """Два пространства: A с админом, руководителем и менеджером; B — со своим."""
    a = await _workspace(db, "Пространство A")
    b = await _workspace(db, "Пространство B")
    await _default_pipeline(db, a)
    await _default_pipeline(db, b)

    a_admin = await _user(db, a.id, "AAdmin", "admin")
    a_head = await _user(db, a.id, "AHead", "head")
    a_mgr = await _user(db, a.id, "AMgr", "manager")
    b_admin = await _user(db, b.id, "BAdmin", "admin")

    a_co = await _company(db, a.id, "Компания A", city="Москва")
    b_co = await _company(db, b.id, "Компания B", city="Казань")
    a_lead = await _lead(db, a.id, "Лид A", owner_id=a_mgr.id, company_id=a_co.id)
    b_lead = await _lead(db, b.id, "Лид B", company_id=b_co.id)
    b_contact = await _contact(db, b.id, b_lead.id, "ЛПР B", email="b@example.com")

    await db.commit()
    return dict(
        a=a, b=b, a_admin=a_admin, a_head=a_head, a_mgr=a_mgr, b_admin=b_admin,
        a_co=a_co, b_co=b_co, a_lead=a_lead, b_lead=b_lead, b_contact=b_contact,
    )


# ===========================================================================
# 1. Кто допущен к маршрутам
# ===========================================================================

@skip_no_pg
@pytest.mark.asyncio
async def test_manager_is_refused_on_every_base_update_route(db, scene, no_queue):
    """Менеджер не допущен ни к одному маршруту домена."""
    s = scene
    job = await _job(db, s["a"].id, s["a_admin"].id)
    rec = await _record(db, job, match_company_id=s["a_co"].id)
    cf = await _conflict(db, job, rec, type_=c.C_FIELD_MISMATCH,
                         target_kind=c.TK_COMPANY, field_name="city", incoming="Тверь")
    await db.commit()

    calls = [
        ("GET", "/api/base-update/jobs", None),
        ("GET", f"/api/base-update/jobs/{job.id}", None),
        ("GET", f"/api/base-update/jobs/{job.id}/conflicts", None),
        ("PATCH", f"/api/base-update/conflicts/{cf.id}", {"resolution": c.R_OVERWRITE}),
        ("POST", f"/api/base-update/jobs/{job.id}/apply", None),
    ]
    for method, path, body in calls:
        r = await call(db, s["a_mgr"], method, path, body)
        assert r.status_code == 403, f"{method} {path} → {r.status_code}"

    r = await call(db, s["a_mgr"], "POST", "/api/base-update/jobs",
                   files={"files": ("карточка.md", "# Компания".encode(), "text/markdown")})
    assert r.status_code == 403
    assert no_queue == []


@skip_no_pg
@pytest.mark.asyncio
async def test_admin_of_another_workspace_sees_nothing(db, scene, no_queue):
    """Чужое пространство получает 404 и не меняет состояние задания."""
    s = scene
    job = await _job(db, s["a"].id, s["a_admin"].id)
    rec = await _record(db, job, match_company_id=s["a_co"].id)
    cf = await _conflict(db, job, rec, type_=c.C_FIELD_MISMATCH,
                         target_kind=c.TK_COMPANY, field_name="city", incoming="Тверь")
    await db.commit()

    assert (await call(db, s["b_admin"], "GET", f"/api/base-update/jobs/{job.id}")).status_code == 404
    assert (await call(db, s["b_admin"], "GET", f"/api/base-update/jobs/{job.id}/conflicts")).status_code == 404
    assert (await call(db, s["b_admin"], "POST", f"/api/base-update/jobs/{job.id}/apply")).status_code == 404
    r = await call(db, s["b_admin"], "PATCH", f"/api/base-update/conflicts/{cf.id}",
                   {"resolution": c.R_OVERWRITE})
    assert r.status_code == 404

    r = await call(db, s["b_admin"], "GET", "/api/base-update/jobs")
    assert r.status_code == 200
    assert [i["id"] for i in r.json()] == []

    await db.refresh(job)
    await db.refresh(cf)
    assert job.status == c.JOB_READY
    assert cf.status == c.CONFLICT_OPEN and cf.resolution is None
    assert no_queue == []


@skip_no_pg
@pytest.mark.asyncio
async def test_owner_admin_walks_the_whole_flow(db, scene, no_queue):
    """Разрешённый контроль: тот же набор запросов реально проходит."""
    s = scene
    job = await _job(db, s["a"].id, s["a_admin"].id)
    rec = await _record(db, job, match_company_id=s["a_co"].id)
    cf = await _conflict(db, job, rec, type_=c.C_FIELD_MISMATCH,
                         target_kind=c.TK_COMPANY, field_name="city", incoming="Тверь")
    await db.commit()

    r = await call(db, s["a_admin"], "GET", "/api/base-update/jobs")
    assert r.status_code == 200 and str(job.id) in r.text

    r = await call(db, s["a_admin"], "GET", f"/api/base-update/jobs/{job.id}/conflicts")
    assert r.status_code == 200 and len(r.json()) == 1

    r = await call(db, s["a_admin"], "PATCH", f"/api/base-update/conflicts/{cf.id}",
                   {"resolution": c.R_OVERWRITE})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == c.CONFLICT_RESOLVED

    # Применение вынесено в отдельную проверку ниже: сейчас этот шаг
    # отвечает ошибкой, хотя задание запускается.


@skip_no_pg
@pytest.mark.asyncio
async def test_head_of_the_same_workspace_may_read_and_resolve(db, scene, no_queue):
    """Фактическая политика домена — на уровне пространства, не автора."""
    s = scene
    job = await _job(db, s["a"].id, s["a_admin"].id)
    rec = await _record(db, job, match_company_id=s["a_co"].id)
    cf = await _conflict(db, job, rec, type_=c.C_FIELD_MISMATCH,
                         target_kind=c.TK_COMPANY, field_name="city", incoming="Тверь")
    await db.commit()

    r = await call(db, s["a_head"], "GET", f"/api/base-update/jobs/{job.id}")
    assert r.status_code == 200
    r = await call(db, s["a_head"], "PATCH", f"/api/base-update/conflicts/{cf.id}",
                   {"resolution": c.R_KEEP})
    assert r.status_code == 200


@skip_no_pg
@pytest.mark.asyncio
async def test_unknown_child_ids_answer_404_without_disclosure(db, scene):
    s = scene
    missing = uuid.uuid4()
    r = await call(db, s["a_admin"], "GET", f"/api/base-update/jobs/{missing}")
    assert r.status_code == 404
    r = await call(db, s["a_admin"], "PATCH", f"/api/base-update/conflicts/{missing}",
                   {"resolution": c.R_KEEP})
    assert r.status_code == 404


@skip_no_pg
@pytest.mark.asyncio
async def test_uploaded_job_takes_workspace_and_author_from_the_actor(db, scene, no_queue):
    """Пространство и владелец берутся из вошедшего, а не из файла."""
    from app.base_update.models import IngestJob
    from sqlalchemy import select

    s = scene
    payload = (
        f"# Компания\nworkspace_id: {s['b'].id}\nuser_id: {s['b_admin'].id}\n"
        f"assigned_to: {s['b_admin'].id}\n"
    ).encode()
    r = await call(db, s["a_admin"], "POST", "/api/base-update/jobs",
                   files={"files": ("карточка.md", payload, "text/markdown")})
    assert r.status_code == 202, r.text
    job_id = uuid.UUID(r.json()["id"])

    job = (await db.execute(select(IngestJob).where(IngestJob.id == job_id))).scalar_one()
    assert job.workspace_id == s["a"].id
    assert job.user_id == s["a_admin"].id
    assert [n for n, _, _ in no_queue] == ["app.scheduled.jobs.base_update_extract"]


@skip_no_pg
@pytest.mark.asyncio
async def test_apply_answers_202_and_really_starts_the_job(db, scene, no_queue):
    """Регрессия SEC-04-1: `/apply` отвечает 202, а не ошибкой.

    Было: `mark_resolving` меняет статус, на UPDATE у `updated_at` стоит
    серверный `onupdate=now()`, SQLAlchemy помечает поле устаревшим, а
    `IngestJobOut` читает его уже после коммита, вне greenlet-контекста.
    Выходило 500 при том, что статус переведён и задача в очереди.

    Стало: значение дочитывается внутри асинхронного контекста, ответ 202
    с актуальным статусом. Побочные эффекты те же: статус в базе и ровно
    одна задача в очереди; повтор по-прежнему даёт 409.

    Это не про доступ — проверка прав отрабатывает раньше.
    """
    from app.base_update.models import IngestJob
    from sqlalchemy import select

    s = scene
    job = await _job(db, s["a"].id, s["a_admin"].id)
    await db.commit()

    r = await call(db, s["a_admin"], "POST", f"/api/base-update/jobs/{job.id}/apply",
                   raise_errors=False)
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["id"] == str(job.id)
    assert body["status"] == c.JOB_RESOLVING
    assert body["updated_at"]

    fresh = (
        await db.execute(select(IngestJob.status).where(IngestJob.id == job.id))
    ).scalar_one()
    assert fresh == c.JOB_RESOLVING
    assert [n for n, _, _ in no_queue] == ["app.scheduled.jobs.base_update_apply"]

    # Повтор: состояние уже изменено, поэтому приходит 409, а не второй запуск.
    r2 = await call(db, s["a_admin"], "POST", f"/api/base-update/jobs/{job.id}/apply",
                    raise_errors=False)
    assert r2.status_code == 409, r2.text
    assert len(no_queue) == 1, "повтор не должен ставить вторую задачу"


# ===========================================================================
# 2. Что worker пишет по решению администратора
# ===========================================================================
#
# Решение по конфликту переносит в запись чужой UUID без проверки:
# `set_match_company` и `set_match_lead` кладут `resolved_value` в
# `match_company_id` / `match_lead_id` как есть. Ниже проверяется, что
# происходит дальше — доходит ли это до чужих данных.

async def run_apply(db, job_id):
    """Настоящий вход worker: пространство он берёт из задания, не из запроса."""
    from app.base_update.orchestrator import run_apply_resolutions

    await run_apply_resolutions(db=db, job_id=job_id)


async def resolve(db, cf, resolution, resolved_value=None):
    cf.resolution = resolution
    cf.resolved_value = resolved_value
    cf.status = c.CONFLICT_RESOLVED
    await db.commit()


@skip_no_pg
@pytest.mark.asyncio
async def test_own_field_overwrite_really_writes(db, scene):
    """Разрешённый контроль для всего блока ниже."""
    s = scene
    job = await _job(db, s["a"].id, s["a_admin"].id)
    rec = await _record(db, job, match_company_id=s["a_co"].id)
    cf = await _conflict(db, job, rec, type_=c.C_FIELD_MISMATCH,
                         target_kind=c.TK_COMPANY, field_name="city", incoming="Тверь")
    await resolve(db, cf, c.R_OVERWRITE)

    await run_apply(db, job.id)

    await db.refresh(s["a_co"])
    assert s["a_co"].city == "Тверь"


@skip_no_pg
@pytest.mark.asyncio
async def test_pick_of_a_foreign_company_is_refused_outright(db, scene):
    """Регрессия SEC-04-2: чужой UUID отвергается там, где приходит.

    Было: `pick` записывал чужой `company_id` в запись как есть, и только
    последующая правка полей упиралась в проверку пространства внутри
    сервиса компаний. Ссылка при этом уже стояла в базе.

    Стало: решение отвергается сразу, запись не меняется, конфликт
    остаётся открытым, чужая компания не тронута.
    """
    s = scene
    job = await _job(db, s["a"].id, s["a_admin"].id)
    rec = await _record(db, job)
    before = rec.match_company_id
    pick = await _conflict(db, job, rec, type_=c.C_COMPANY_AMBIGUOUS,
                           target_kind=c.TK_COMPANY)
    await resolve(db, pick, c.R_PICK, str(s["b_co"].id))
    await run_apply(db, job.id)

    await db.refresh(rec)
    assert rec.match_company_id == before, "чужой UUID всё-таки записан"
    assert "workspace" in (rec.error or ""), rec.error
    await db.refresh(pick)
    assert pick.status == c.CONFLICT_OPEN
    await db.refresh(s["b_co"])
    assert s["b_co"].city == "Казань", "чужая компания изменена"


@skip_no_pg
@pytest.mark.asyncio
async def test_pick_of_an_own_company_goes_through(db, scene):
    """Разрешённый контроль: своя компания выбирается и правится."""
    s = scene
    job = await _job(db, s["a"].id, s["a_admin"].id)
    rec = await _record(db, job)
    pick = await _conflict(db, job, rec, type_=c.C_COMPANY_AMBIGUOUS,
                           target_kind=c.TK_COMPANY)
    await resolve(db, pick, c.R_PICK, str(s["a_co"].id))
    await run_apply(db, job.id)

    await db.refresh(rec)
    assert rec.match_company_id == s["a_co"].id, rec.error

    field = await _conflict(db, job, rec, type_=c.C_FIELD_MISMATCH,
                            target_kind=c.TK_COMPANY, field_name="city",
                            incoming="Тверь")
    await resolve(db, field, c.R_OVERWRITE)
    await run_apply(db, job.id)

    await db.refresh(s["a_co"])
    assert s["a_co"].city == "Тверь"


@skip_no_pg
@pytest.mark.asyncio
async def test_new_lead_cannot_point_at_a_foreign_company(db, scene):
    """Регрессия SEC-04-2: ссылка на компанию проверяется по пространству.

    Было: `create_new_lead` брал `match_company_id` как есть, и карточка
    пространства A могла ссылаться на компанию пространства B.
    Содержимое соседа при этом не раскрывалось, но ссылка в базе
    оставалась.

    Стало: перед записью проверяется принадлежность компании пространству
    задания; запись не создаётся, у строки появляется внятная ошибка.
    """
    from sqlalchemy import func, select

    from app.leads.models import Lead

    s = scene
    job = await _job(db, s["a"].id, s["a_admin"].id)
    rec = await _record(db, job, match_company_id=s["b_co"].id, name="Пришлая")
    target = await _conflict(db, job, rec, type_=c.C_LEAD_TARGET, target_kind=c.TK_LEAD)
    await resolve(db, target, c.R_KEEP)

    before = (await db.execute(select(func.count(Lead.id)))).scalar_one()
    await run_apply(db, job.id)

    await db.refresh(rec)
    assert rec.match_lead_id is None, "карточка создана по чужой ссылке"
    assert "workspace" in (rec.error or ""), rec.error
    after = (await db.execute(select(func.count(Lead.id)))).scalar_one()
    assert after == before, "лишняя карточка всё-таки записана"


@skip_no_pg
@pytest.mark.asyncio
async def test_new_lead_is_created_for_a_company_of_its_own_workspace(db, scene):
    """Разрешённый контроль к предыдущей проверке: своя компания проходит."""
    from sqlalchemy import select

    from app.leads.models import Lead

    s = scene
    job = await _job(db, s["a"].id, s["a_admin"].id)
    rec = await _record(db, job, match_company_id=s["a_co"].id, name="Своя")
    target = await _conflict(db, job, rec, type_=c.C_LEAD_TARGET, target_kind=c.TK_LEAD)
    await resolve(db, target, c.R_KEEP)

    await run_apply(db, job.id)

    await db.refresh(rec)
    assert rec.match_lead_id is not None, rec.error
    created = (
        await db.execute(select(Lead).where(Lead.id == rec.match_lead_id))
    ).scalar_one()
    assert created.workspace_id == s["a"].id
    assert created.company_id == s["a_co"].id


@skip_no_pg
@pytest.mark.asyncio
async def test_contact_cannot_be_added_to_a_foreign_lead(db, scene):
    """`add_contact` по чужому `match_lead_id` не создаёт строку у соседа."""
    from sqlalchemy import func, select

    from app.contacts.models import Contact

    s = scene
    before = (
        await db.execute(
            select(func.count()).select_from(Contact).where(Contact.lead_id == s["b_lead"].id)
        )
    ).scalar_one()

    job = await _job(db, s["a"].id, s["a_admin"].id)
    rec = await _record(db, job, match_lead_id=s["b_lead"].id)
    cf = await _conflict(db, job, rec, type_=c.C_CONTACT_MISMATCH,
                         target_kind=c.TK_CONTACT,
                         candidates=[{"name": "Подставной ЛПР", "email": "x@example.com"}])
    await resolve(db, cf, c.R_ADD_SEPARATE)

    await run_apply(db, job.id)

    after = (
        await db.execute(
            select(func.count()).select_from(Contact).where(Contact.lead_id == s["b_lead"].id)
        )
    ).scalar_one()
    assert after == before, "контакт добавлен к чужой карточке"
    await db.refresh(rec)
    assert rec.error and "add_contact failed" in rec.error


@skip_no_pg
@pytest.mark.asyncio
async def test_foreign_contact_field_is_not_overwritten(db, scene):
    """`overwrite` по чужому `contact_id` не меняет чужой контакт."""
    s = scene
    job = await _job(db, s["a"].id, s["a_admin"].id)
    rec = await _record(db, job, match_lead_id=s["b_lead"].id)
    cf = await _conflict(db, job, rec, type_=c.C_CONTACT_MISMATCH,
                         target_kind=c.TK_CONTACT, field_name="email",
                         incoming="attacker@example.com")
    await resolve(db, cf, c.R_OVERWRITE, str(s["b_contact"].id))

    await run_apply(db, job.id)

    await db.refresh(s["b_contact"])
    assert s["b_contact"].email == "b@example.com"
    await db.refresh(rec)
    assert rec.error and "update_contact failed" in rec.error


@skip_no_pg
@pytest.mark.asyncio
async def test_worker_takes_the_workspace_from_the_job(db, scene):
    """Пространство worker берёт из задания — подменить его нечем.

    Прямой вызов сервиса с чужим пространством не находит задание и
    ничего не пишет.
    """
    from app.base_update import services as svc

    s = scene
    job = await _job(db, s["a"].id, s["a_admin"].id)
    rec = await _record(db, job, match_company_id=s["a_co"].id)
    cf = await _conflict(db, job, rec, type_=c.C_FIELD_MISMATCH,
                         target_kind=c.TK_COMPANY, field_name="city", incoming="Тверь")
    await resolve(db, cf, c.R_OVERWRITE)

    with pytest.raises(ValueError):
        await svc.apply_resolutions(db, workspace_id=s["b"].id, job_id=job.id)

    await db.refresh(s["a_co"])
    assert s["a_co"].city == "Москва"
