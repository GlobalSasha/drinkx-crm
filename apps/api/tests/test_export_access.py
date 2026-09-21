"""Кто что может выгрузить (аудит G6, ревью доступа).

`POST /api/export` принимал `filters` как есть, а worker сверял только
рабочее пространство. Менеджер мог попросить `assignment_status=pool` и
получить базу лидов, закрытую для него с 2026-09-14, либо подставить
`assigned_to` коллеги. Готовую выгрузку тоже мог скачать любой из
пространства: `GET /api/export/{id}` и `/download` не смотрели на автора.

Проверки идут через HTTP: правило живёт на входе в эндпоинт, и то, что
сохраняется в `filters_json`, — часть контракта.
"""
from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

import app.main  # noqa: F401  — настраивает мапперы SQLAlchemy
from tests.conftest import POSTGRES_AVAILABLE

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires PostgreSQL")


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


async def _lead(db, workspace_id, *, name: str, assigned_to=None, pool=False):
    from app.leads.models import Lead

    lead = Lead(
        workspace_id=workspace_id,
        company_name=name,
        assignment_status="pool" if pool else "assigned",
        assigned_to=None if pool else assigned_to,
    )
    db.add(lead)
    await db.flush()
    return lead


async def _call(db, actor, method: str, path: str, **kwargs):
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


async def _create_export(db, actor, filters: dict | None):
    """POST /api/export.

    Отправку в Celery подменяем: брокера в тестах нет, а `send_task`
    уходит в собственные повторы подключения и висит. Роутер и так
    глушит её исключения — проверяем мы не доставку, а права.
    """
    from app.scheduled.celery_app import celery_app

    orig = celery_app.send_task
    celery_app.send_task = lambda *a, **kw: None
    try:
        return await _call(
            db, actor, "POST", "/api/export",
            json={"format": "csv", "filters": filters or {}, "include_ai_brief": False},
        )
    finally:
        celery_app.send_task = orig


async def _job(db, job_id):
    from sqlalchemy import select

    from app.import_export.models import ExportJob

    return (
        await db.execute(select(ExportJob).where(ExportJob.id == uuid.UUID(job_id)))
    ).scalar_one()


# ---------------------------------------------------------------------------
# Создание задачи: чей фильтр сохраняется
# ---------------------------------------------------------------------------


@skip_no_pg
@pytest.mark.asyncio
async def test_a_manager_without_filters_is_scoped_to_themselves(db, workspace):
    """Пустой фильтр не означает «всё пространство»."""
    manager = await _user(db, workspace.id, "manager", "Manager")

    res = await _create_export(db, manager, {})
    assert res.status_code == 202, res.text

    job = await _job(db, res.json()["id"])
    assert job.filters_json["assigned_to"] == str(manager.id)
    assert job.filters_json["assignment_status"] == "assigned"


@skip_no_pg
@pytest.mark.asyncio
async def test_a_manager_may_ask_for_their_own_leads(db, workspace):
    manager = await _user(db, workspace.id, "manager", "Manager")

    res = await _create_export(
        db, manager, {"assigned_to": str(manager.id), "city": "Москва"}
    )
    assert res.status_code == 202, res.text

    job = await _job(db, res.json()["id"])
    assert job.filters_json["assigned_to"] == str(manager.id)
    # Обычные фильтры остаются как есть.
    assert job.filters_json["cities"] == ["Москва"]


@skip_no_pg
@pytest.mark.asyncio
async def test_a_manager_cannot_export_a_colleagues_leads(db, workspace):
    manager = await _user(db, workspace.id, "manager", "Manager")
    peer = await _user(db, workspace.id, "manager", "Peer")

    res = await _create_export(db, manager, {"assigned_to": str(peer.id)})
    assert res.status_code == 403, res.text
    # Отказ, а не молча своя выборка: иначе человек решит, что выгрузил
    # чужие карточки, и не заметит подмены.
    assert "чуж" in res.json()["detail"].lower()


@skip_no_pg
@pytest.mark.asyncio
async def test_a_manager_cannot_export_the_pool(db, workspace):
    manager = await _user(db, workspace.id, "manager", "Manager")

    res = await _create_export(db, manager, {"assignment_status": "pool"})
    assert res.status_code == 403, res.text

    # И никакой задачи не создалось.
    from sqlalchemy import func, select

    from app.import_export.models import ExportJob

    # По этому пространству — ни одной: `create_export_job` коммитит, и
    # считать по всей таблице нельзя, там лежат задачи соседних проверок.
    count = (
        await db.execute(
            select(func.count())
            .select_from(ExportJob)
            .where(ExportJob.workspace_id == workspace.id)
        )
    ).scalar_one()
    assert count == 0


@skip_no_pg
@pytest.mark.asyncio
async def test_the_head_and_the_admin_may_export_the_pool(db, workspace):
    for role in ("head", "admin"):
        actor = await _user(db, workspace.id, role, f"Boss{role}")
        res = await _create_export(db, actor, {"assignment_status": "pool"})
        assert res.status_code == 202, (role, res.text)
        job = await _job(db, res.json()["id"])
        assert job.filters_json["assignment_status"] == "pool"
        assert "assigned_to" not in job.filters_json


@skip_no_pg
@pytest.mark.asyncio
async def test_the_head_may_name_another_assignee_from_the_same_workspace(db, workspace):
    head = await _user(db, workspace.id, "head", "Head")
    manager = await _user(db, workspace.id, "manager", "Manager")

    res = await _create_export(db, head, {"assigned_to": str(manager.id)})
    assert res.status_code == 202, res.text
    job = await _job(db, res.json()["id"])
    assert job.filters_json["assigned_to"] == str(manager.id)


@skip_no_pg
@pytest.mark.asyncio
async def test_an_assignee_from_another_workspace_is_rejected_not_ignored(db, workspace):
    """Иначе фильтр молча ничего не находит и выглядит как «у сотрудника
    нет карточек»."""
    from app.auth.models import Workspace

    head = await _user(db, workspace.id, "head", "Head")
    other_ws = Workspace(name="Other WS", plan="free")
    db.add(other_ws)
    await db.flush()
    outsider = await _user(db, other_ws.id, "manager", "Outsider")

    res = await _create_export(db, head, {"assigned_to": str(outsider.id)})
    assert res.status_code == 422, res.text


# ---------------------------------------------------------------------------
# Что выгрузка реально содержит
# ---------------------------------------------------------------------------


async def _export_ids(db, job_id) -> set:
    """Прогоняет настоящую задачу экспорта и собирает выгруженные строки."""
    from app.import_export import exporters as exporters_mod
    from app.import_export import redis_bytes as redis_mod
    from app.scheduled import jobs as jobs_mod

    exported: list = []
    real_rows = exporters_mod.leads_to_rows

    def _recording(leads, **kwargs):
        exported.extend(leads)
        return real_rows(leads, **kwargs)

    class _Holder:
        async def __aenter__(self_inner):
            return db

        async def __aexit__(self_inner, *exc):
            return False

    class _Engine:
        async def dispose(self_inner):
            return None

    async def _fake_store(jid, payload):
        return f"export:{jid}"

    exporters_mod.leads_to_rows = _recording
    orig_factory = jobs_mod._build_task_engine_and_factory
    jobs_mod._build_task_engine_and_factory = lambda: (_Engine(), lambda: _Holder())
    orig_store = redis_mod.store_export_bytes
    redis_mod.store_export_bytes = _fake_store
    try:
        result = await jobs_mod._run_export(uuid.UUID(str(job_id)))
    finally:
        exporters_mod.leads_to_rows = real_rows
        jobs_mod._build_task_engine_and_factory = orig_factory
        redis_mod.store_export_bytes = orig_store
    assert "error" not in result, result
    return {lead.id for lead in exported}


@skip_no_pg
@pytest.mark.asyncio
async def test_a_managers_export_contains_only_their_own_leads(db, workspace):
    manager = await _user(db, workspace.id, "manager", "Manager")
    peer = await _user(db, workspace.id, "manager", "Peer")

    mine = await _lead(db, workspace.id, name="Моя", assigned_to=manager.id)
    theirs = await _lead(db, workspace.id, name="Чужая", assigned_to=peer.id)
    in_pool = await _lead(db, workspace.id, name="В базе", pool=True)

    res = await _create_export(db, manager, {})
    assert res.status_code == 202
    exported = await _export_ids(db, res.json()["id"])

    assert exported == {mine.id}
    assert theirs.id not in exported and in_pool.id not in exported


@skip_no_pg
@pytest.mark.asyncio
async def test_the_head_exports_the_whole_workspace(db, workspace):
    head = await _user(db, workspace.id, "head", "Head")
    manager = await _user(db, workspace.id, "manager", "Manager")

    assigned = await _lead(db, workspace.id, name="Назначена", assigned_to=manager.id)
    in_pool = await _lead(db, workspace.id, name="В базе", pool=True)

    res = await _create_export(db, head, {})
    assert res.status_code == 202
    exported = await _export_ids(db, res.json()["id"])
    assert exported == {assigned.id, in_pool.id}


@skip_no_pg
@pytest.mark.asyncio
async def test_an_export_never_crosses_a_workspace(db, workspace):
    from app.auth.models import Workspace

    head = await _user(db, workspace.id, "head", "Head")
    mine = await _lead(db, workspace.id, name="Наша", pool=True)

    other_ws = Workspace(name="Other WS", plan="free")
    db.add(other_ws)
    await db.flush()
    await _lead(db, other_ws.id, name="Чужая", pool=True)

    res = await _create_export(db, head, {})
    exported = await _export_ids(db, res.json()["id"])
    assert exported == {mine.id}


# ---------------------------------------------------------------------------
# Доступ к готовой задаче и файлу
# ---------------------------------------------------------------------------


@skip_no_pg
@pytest.mark.asyncio
async def test_a_manager_cannot_read_or_download_someone_elses_export(db, workspace):
    manager = await _user(db, workspace.id, "manager", "Manager")
    peer = await _user(db, workspace.id, "manager", "Peer")
    head = await _user(db, workspace.id, "head", "Head")

    peers_job = (await _create_export(db, peer, {})).json()["id"]
    heads_job = (await _create_export(db, head, {})).json()["id"]

    for job_id, whose in ((peers_job, "коллеги"), (heads_job, "руководителя")):
        got = await _call(db, manager, "GET", f"/api/export/{job_id}")
        assert got.status_code == 404, whose
        dl = await _call(db, manager, "GET", f"/api/export/{job_id}/download")
        assert dl.status_code == 404, whose


@skip_no_pg
@pytest.mark.asyncio
async def test_a_manager_reads_their_own_export(db, workspace):
    manager = await _user(db, workspace.id, "manager", "Manager")
    job_id = (await _create_export(db, manager, {})).json()["id"]

    got = await _call(db, manager, "GET", f"/api/export/{job_id}")
    assert got.status_code == 200
    assert got.json()["id"] == job_id

    # Файла ещё нет: задача не выполнялась. Это 409, а не отказ в доступе.
    dl = await _call(db, manager, "GET", f"/api/export/{job_id}/download")
    assert dl.status_code == 409


@skip_no_pg
@pytest.mark.asyncio
async def test_the_head_reads_a_managers_export(db, workspace):
    """Административная модель прежняя: руководитель видит пространство."""
    head = await _user(db, workspace.id, "head", "Head")
    manager = await _user(db, workspace.id, "manager", "Manager")

    job_id = (await _create_export(db, manager, {})).json()["id"]
    got = await _call(db, head, "GET", f"/api/export/{job_id}")
    assert got.status_code == 200


@skip_no_pg
@pytest.mark.asyncio
async def test_an_export_from_another_workspace_is_404(db, workspace):
    from app.auth.models import Workspace

    head = await _user(db, workspace.id, "head", "Head")
    job_id = (await _create_export(db, head, {})).json()["id"]

    other_ws = Workspace(name="Other WS", plan="free")
    db.add(other_ws)
    await db.flush()
    outsider = await _user(db, other_ws.id, "admin", "Outsider")

    got = await _call(db, outsider, "GET", f"/api/export/{job_id}")
    assert got.status_code == 404
    dl = await _call(db, outsider, "GET", f"/api/export/{job_id}/download")
    assert dl.status_code == 404


@skip_no_pg
@pytest.mark.asyncio
async def test_an_authorless_job_is_not_visible_to_a_manager(db, workspace):
    """`user_id` в таблице nullable. Старые строки без автора не должны
    становиться общедоступными."""
    from app.import_export.models import ExportJob

    manager = await _user(db, workspace.id, "manager", "Manager")
    head = await _user(db, workspace.id, "head", "Head")
    orphan = ExportJob(
        workspace_id=workspace.id,
        user_id=None,
        status="pending",
        format="csv",
        filters_json={},
    )
    db.add(orphan)
    await db.flush()

    assert (
        await _call(db, manager, "GET", f"/api/export/{orphan.id}")
    ).status_code == 404
    assert (
        await _call(db, head, "GET", f"/api/export/{orphan.id}")
    ).status_code == 200
