"""SEC-06 — обычный импорт на корректных состояниях.

SEC-02 закрыл вопрос «кому видно и кому можно». Здесь проверяется то, что
осталось: проходит ли разрешённый сценарий до конца и совпадают ли
обещания предпросмотра с тем, что worker действительно записал.

Настоящий локальный путь: `upload → confirm-mapping → apply → запись в
worker`. Код 202 подтверждает только запуск — успех проверяется
состоянием базы после прогона исполнителя.

Очередь заменена записывающей заглушкой; worker вызывается явно на той
же тестовой сессии. Политика доступа здесь не переписывается — берутся
только те проверки, где есть иной путь записи или корректное состояние.
"""
from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

import app.main  # noqa: F401 — настраивает мапперы SQLAlchemy
# Отдельный прогон этого файла создаёт схему только из импортированных
# моделей (известное P2-5). Worker импорта пишет в справочники UTM, и без
# явного импорта их таблиц не будет — тогда каждая строка «падает» по
# несуществующей таблице, а не по проверяемому правилу.
import app.utm.models  # noqa: F401
from tests.conftest import POSTGRES_AVAILABLE

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires PostgreSQL")

HEADER = "Компания;Город;Email\n"


def csv_bytes(rows: list[tuple[str, str, str]]) -> bytes:
    body = HEADER + "".join(f"{a};{b};{c}\n" for a, b, c in rows)
    return body.encode("utf-8")


# --- обвязка ---------------------------------------------------------------

async def _workspace(db, name: str):
    from app.auth.models import Workspace

    ws = Workspace(name=name, plan="pro", sprint_capacity_per_week=20)
    db.add(ws)
    await db.flush()
    return ws


async def _user(db, workspace_id, name: str, role: str = "manager"):
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


async def _lead(db, workspace_id, name, owner_id=None, city=None):
    from app.leads import repositories as repo

    data = dict(company_name=name)
    if city is not None:
        data["city"] = city
    return await repo.create_lead(
        db, workspace_id, data,
        assigned_to=owner_id,
        assignment_status="assigned" if owner_id else "pool",
    )


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
    from app.scheduled.celery_app import celery_app

    sent: list[str] = []
    monkeypatch.setattr(celery_app, "send_task", lambda name, *a, **kw: sent.append(name))
    return sent


async def run_import_worker(db, job_id):
    """Настоящий `_run_bulk_import` на тестовой сессии."""
    from app.scheduled import jobs as jobs_mod

    class _Holder:
        async def __aenter__(self_inner):
            return db

        async def __aexit__(self_inner, *exc):
            return False

    class _Engine:
        async def dispose(self_inner):
            return None

    orig = jobs_mod._build_task_engine_and_factory
    jobs_mod._build_task_engine_and_factory = lambda: (_Engine(), lambda: _Holder())
    try:
        return await jobs_mod._run_bulk_import(job_id)
    finally:
        jobs_mod._build_task_engine_and_factory = orig


async def upload_csv(db, actor, rows, filename="импорт.csv"):
    return await call(
        db, actor, "POST", "/api/import/upload",
        files={"file": (filename, csv_bytes(rows), "text/csv")},
    )


MAPPING = {"Компания": "company_name", "Город": "city", "Email": "email"}


@pytest.fixture
async def scene(db):
    a = await _workspace(db, "Пространство A")
    b = await _workspace(db, "Пространство B")
    await _default_pipeline(db, a)
    await _default_pipeline(db, b)
    owner = await _user(db, a.id, "Owner")
    stranger = await _user(db, a.id, "Stranger")
    head = await _user(db, a.id, "Head", "head")
    outsider = await _user(db, b.id, "Outsider", "admin")
    a_lead = await _lead(db, a.id, "Существующая A", owner.id, city="Москва")
    b_lead = await _lead(db, b.id, "Существующая B", city="Казань")
    await db.commit()
    return dict(a=a, b=b, owner=owner, stranger=stranger, head=head,
                outsider=outsider, a_lead=a_lead, b_lead=b_lead)


async def leads_of(db, workspace_id):
    from sqlalchemy import select

    from app.leads.models import Lead

    rows = (
        await db.execute(
            select(Lead.company_name).where(Lead.workspace_id == workspace_id)
        )
    ).scalars().all()
    return sorted(rows)


# ===========================================================================
# 1. Разрешённый сценарий целиком
# ===========================================================================

@skip_no_pg
@pytest.mark.asyncio
async def test_owner_manager_completes_the_import(db, scene, no_queue):
    from sqlalchemy import select

    from app.import_export.models import ImportJob
    from app.leads.models import Lead

    s = scene
    r = await upload_csv(db, s["owner"], [("Ромашка", "Тверь", "a@example.com"),
                                          ("Василёк", "Тула", "b@example.com")])
    assert r.status_code == 200, r.text
    job_id = uuid.UUID(r.json()["id"])
    assert r.json()["status"] == "uploaded"
    assert r.json()["total_rows"] == 2

    r = await call(db, s["owner"], "POST", f"/api/import/jobs/{job_id}/confirm-mapping",
                   {"mapping": MAPPING})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "previewed"

    r = await call(db, s["owner"], "POST", f"/api/import/jobs/{job_id}/apply")
    assert r.status_code == 202, r.text
    assert no_queue == ["app.scheduled.jobs.bulk_import_run"]

    # 202 — это только запуск. Успех подтверждается состоянием базы.
    result = await run_import_worker(db, job_id)
    assert result["succeeded"] == 2 and result["failed"] == 0

    job = (await db.execute(select(ImportJob).where(ImportJob.id == job_id))).scalar_one()
    assert job.status == "succeeded"
    assert (job.succeeded, job.failed, job.processed) == (2, 0, 2)

    created = (
        await db.execute(
            select(Lead).where(Lead.workspace_id == s["a"].id,
                               Lead.company_name.in_(["Ромашка", "Василёк"]))
        )
    ).scalars().all()
    assert len(created) == 2
    for lead in created:
        assert lead.workspace_id == s["a"].id
        assert lead.assignment_status == "pool"
        assert lead.assigned_to is None
        assert lead.pipeline_id is not None and lead.stage_id is not None


@skip_no_pg
@pytest.mark.asyncio
async def test_import_creates_and_never_touches_existing_cards(db, scene, no_queue):
    """Свой импорт не переписывает ни свою старую карточку, ни чужую."""
    from sqlalchemy import select

    from app.leads.models import Lead

    s = scene
    r = await upload_csv(db, s["owner"], [
        ("Существующая A", "Сочи", "x@example.com"),
        ("Существующая B", "Сочи", "y@example.com"),
    ])
    job_id = uuid.UUID(r.json()["id"])
    await call(db, s["owner"], "POST", f"/api/import/jobs/{job_id}/confirm-mapping",
               {"mapping": MAPPING})
    await call(db, s["owner"], "POST", f"/api/import/jobs/{job_id}/apply")
    await run_import_worker(db, job_id)

    await db.refresh(s["a_lead"])
    await db.refresh(s["b_lead"])
    assert s["a_lead"].city == "Москва", "старая карточка переписана"
    assert s["b_lead"].city == "Казань", "чужая карточка переписана"

    assert await leads_of(db, s["b"].id) == ["Существующая B"]
    same_name = (
        await db.execute(
            select(Lead).where(Lead.workspace_id == s["a"].id,
                               Lead.company_name == "Существующая A")
        )
    ).scalars().all()
    assert len(same_name) == 2, "новая карточка не создана — контроль потерян"


# ===========================================================================
# 2. Счётчики
# ===========================================================================

@skip_no_pg
@pytest.mark.asyncio
async def test_counters_have_no_double_accounting(db, scene, no_queue):
    from sqlalchemy import func, select

    from app.import_export.models import ImportError, ImportJob

    s = scene
    r = await upload_csv(db, s["owner"], [
        ("Хорошая", "Тверь", "ok@example.com"),
        ("", "Тула", "empty@example.com"),          # пустое название — отказ
    ])
    job_id = uuid.UUID(r.json()["id"])
    await call(db, s["owner"], "POST", f"/api/import/jobs/{job_id}/confirm-mapping",
               {"mapping": MAPPING})
    await call(db, s["owner"], "POST", f"/api/import/jobs/{job_id}/apply")
    await run_import_worker(db, job_id)

    job = (await db.execute(select(ImportJob).where(ImportJob.id == job_id))).scalar_one()
    assert (job.succeeded, job.failed) == (1, 1)
    assert job.processed == job.succeeded + job.failed == 2
    assert job.status == "failed" and job.error_summary

    errors = (
        await db.execute(
            select(func.count()).select_from(ImportError).where(ImportError.job_id == job_id)
        )
    ).scalar_one()
    assert errors == 1


@skip_no_pg
@pytest.mark.asyncio
async def test_worker_keeps_the_skip_the_preview_promised(db, scene, no_queue):
    """Регрессия SEC-06-1: предпросмотр и результат сходятся.

    Было: `confirm-mapping` считал строку с негодным email в
    `will_skip`, а worker проверку не повторял и карточку всё-таки
    создавал — предпросмотр обещал одно, импорт делал другое.

    Стало: worker прогоняет те же правила, строка уходит в отказ с
    внятной ошибкой, годная строка при этом заводится.
    """
    from sqlalchemy import select

    from app.import_export.models import ImportError, ImportJob
    from app.leads.models import Lead

    s = scene
    r = await upload_csv(db, s["owner"], [
        ("Хорошая", "Тверь", "ok@example.com"),
        ("С кривой почтой", "Тула", "не-почта"),
    ])
    job_id = uuid.UUID(r.json()["id"])
    r = await call(db, s["owner"], "POST", f"/api/import/jobs/{job_id}/confirm-mapping",
                   {"mapping": MAPPING})
    assert r.status_code == 200

    job = (await db.execute(select(ImportJob).where(ImportJob.id == job_id))).scalar_one()
    stats = (job.diff_json or {})["dry_run_stats"]
    assert (stats["will_create"], stats["will_skip"]) == (1, 1)

    await call(db, s["owner"], "POST", f"/api/import/jobs/{job_id}/apply")
    await run_import_worker(db, job_id)

    await db.refresh(job)
    assert (job.succeeded, job.failed) == (stats["will_create"], stats["will_skip"])
    assert job.processed == job.succeeded + job.failed == job.total_rows

    bad = (
        await db.execute(
            select(Lead).where(Lead.workspace_id == s["a"].id,
                               Lead.company_name == "С кривой почтой")
        )
    ).scalar_one_or_none()
    assert bad is None, "строка, обещанная пропущенной, всё-таки заведена"

    good = (
        await db.execute(
            select(Lead).where(Lead.workspace_id == s["a"].id,
                               Lead.company_name == "Хорошая")
        )
    ).scalar_one_or_none()
    assert good is not None, "годная строка не заведена"

    errs = list((await db.execute(
        select(ImportError).where(ImportError.job_id == job_id)
    )).scalars())
    assert [e.field for e in errs] == ["validation"]


# ===========================================================================
# 3. Кто может вести чужое задание
# ===========================================================================

@skip_no_pg
@pytest.mark.asyncio
async def test_another_manager_cannot_read_change_or_run_the_job(db, scene, no_queue):
    from sqlalchemy import select

    from app.import_export.models import ImportJob

    s = scene
    r = await upload_csv(db, s["owner"], [("Ромашка", "Тверь", "a@example.com")])
    job_id = uuid.UUID(r.json()["id"])

    for method, path, body in (
        ("GET", f"/api/import/jobs/{job_id}", None),
        ("POST", f"/api/import/jobs/{job_id}/confirm-mapping", {"mapping": MAPPING}),
        ("POST", f"/api/import/jobs/{job_id}/cancel", None),
        ("POST", f"/api/import/jobs/{job_id}/apply", None),
    ):
        for actor in (s["stranger"], s["outsider"]):
            r = await call(db, actor, method, path, body)
            assert r.status_code == 404, (actor.name, method, path, r.status_code)

    r = await call(db, s["stranger"], "GET", "/api/import/jobs")
    assert r.status_code == 200 and r.json()["total"] == 0

    job = (await db.execute(select(ImportJob).where(ImportJob.id == job_id))).scalar_one()
    assert job.status == "uploaded"
    assert no_queue == []


@skip_no_pg
@pytest.mark.asyncio
async def test_head_may_drive_someone_elses_job(db, scene, no_queue):
    """Фактическая политика: руководителю доступна любая задача в пространстве."""
    s = scene
    r = await upload_csv(db, s["owner"], [("Ромашка", "Тверь", "a@example.com")])
    job_id = uuid.UUID(r.json()["id"])

    assert (await call(db, s["head"], "GET", f"/api/import/jobs/{job_id}")).status_code == 200
    r = await call(db, s["head"], "POST", f"/api/import/jobs/{job_id}/confirm-mapping",
                   {"mapping": MAPPING})
    assert r.status_code == 200
    r = await call(db, s["head"], "POST", f"/api/import/jobs/{job_id}/apply")
    assert r.status_code == 202


# ===========================================================================
# 4. Автор задания меняется до исполнения
# ===========================================================================

@skip_no_pg
@pytest.mark.asyncio
async def test_worker_rechecks_the_author_before_every_row(db, scene, no_queue):
    """Регрессия SEC-06-2: автор перепроверяется перед каждой строкой.

    Было: обычный импорт использовал `user_id` только как автора
    комментария и после `apply` на автора уже не смотрел. В bulk-update
    это исправлено (SEC2-F1), здесь — нет.

    Стало: перед каждой строкой читаются действующие данные автора.
    Проверяется случай, у которого в этом продукте есть смысл: автора
    перевели в другое пространство. Роль здесь не ворота — обычный
    импорт ролью не ограничен вовсе (это открытый P2-13, отдельная
    задача), поэтому «отозванную роль» здесь нечем воспроизвести.
    """
    from sqlalchemy import func, select, update

    from app.auth.models import User
    from app.import_export.models import ImportError, ImportJob
    from app.leads.models import Lead

    s = scene
    r = await upload_csv(db, s["owner"], [("После перевода", "Тверь", "a@example.com")])
    job_id = uuid.UUID(r.json()["id"])
    await call(db, s["owner"], "POST", f"/api/import/jobs/{job_id}/confirm-mapping",
               {"mapping": MAPPING})
    await call(db, s["owner"], "POST", f"/api/import/jobs/{job_id}/apply")

    before = (await db.execute(select(func.count(Lead.id)))).scalar_one()

    # Автор переведён в другое пространство уже после постановки в очередь.
    await db.execute(
        update(User).where(User.id == s["owner"].id).values(workspace_id=s["b"].id)
    )
    await db.commit()

    await run_import_worker(db, job_id)

    job = (await db.execute(select(ImportJob).where(ImportJob.id == job_id))).scalar_one()
    await db.refresh(job)
    assert (job.succeeded, job.failed) == (0, 1)
    assert job.processed == 1, "строка посчитана дважды"
    assert (await db.execute(select(func.count(Lead.id)))).scalar_one() == before

    errs = list((await db.execute(
        select(ImportError).where(ImportError.job_id == job_id)
    )).scalars())
    assert [e.field for e in errs] == ["access"]


@skip_no_pg
@pytest.mark.asyncio
async def test_own_author_still_completes_the_import(db, scene, no_queue):
    """Разрешённый контроль: автор на месте — импорт доходит до записи."""
    from sqlalchemy import select

    from app.import_export.models import ImportJob
    from app.leads.models import Lead

    s = scene
    r = await upload_csv(db, s["owner"], [("Всё в порядке", "Тверь", "a@example.com")])
    job_id = uuid.UUID(r.json()["id"])
    await call(db, s["owner"], "POST", f"/api/import/jobs/{job_id}/confirm-mapping",
               {"mapping": MAPPING})
    await call(db, s["owner"], "POST", f"/api/import/jobs/{job_id}/apply")
    await run_import_worker(db, job_id)

    job = (await db.execute(select(ImportJob).where(ImportJob.id == job_id))).scalar_one()
    await db.refresh(job)
    assert (job.succeeded, job.failed) == (1, 0)
    assert (
        await db.execute(
            select(Lead).where(Lead.workspace_id == s["a"].id,
                               Lead.company_name == "Всё в порядке")
        )
    ).scalar_one_or_none() is not None


@skip_no_pg
@pytest.mark.asyncio
async def test_deleted_author_stops_the_job_instead_of_writing(db, scene, no_queue):
    """Регрессия SEC-06-3: без автора задание не пишет.

    Было: `ON DELETE SET NULL` обнулял ссылку, и импорт молча
    продолжался — записи заводил никто. Стало: строки уходят в отказ.
    Подставлять вместо удалённого автора admin нельзя, отдельного
    системного актора в этом worker нет; если такой понадобится, это
    отдельное решение, а не умолчание.
    """
    from sqlalchemy import delete, func, select

    from app.auth.models import User
    from app.import_export.models import ImportError, ImportJob
    from app.leads.models import Lead

    s = scene
    worker_user = await _user(db, s["a"].id, "Temp")
    await db.commit()

    r = await upload_csv(db, worker_user, [("После удаления", "Тверь", "a@example.com")])
    job_id = uuid.UUID(r.json()["id"])
    await call(db, worker_user, "POST", f"/api/import/jobs/{job_id}/confirm-mapping",
               {"mapping": MAPPING})
    await call(db, worker_user, "POST", f"/api/import/jobs/{job_id}/apply")

    await db.execute(delete(User).where(User.id == worker_user.id))
    await db.commit()

    job = (await db.execute(select(ImportJob).where(ImportJob.id == job_id))).scalar_one()
    await db.refresh(job)
    assert job.user_id is None

    before = (await db.execute(select(func.count(Lead.id)))).scalar_one()
    await run_import_worker(db, job_id)
    await db.refresh(job)

    assert (job.succeeded, job.failed) == (0, 1)
    assert (await db.execute(select(func.count(Lead.id)))).scalar_one() == before
    assert (
        await db.execute(
            select(Lead).where(Lead.workspace_id == s["a"].id,
                               Lead.company_name == "После удаления")
        )
    ).scalar_one_or_none() is None
    errs = list((await db.execute(
        select(ImportError).where(ImportError.job_id == job_id)
    )).scalars())
    assert [e.field for e in errs] == ["access"]

