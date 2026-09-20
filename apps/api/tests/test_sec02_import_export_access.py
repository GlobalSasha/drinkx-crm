"""SEC-02: снимок, задачи импорта и цели массового обновления.

До правки: менеджер получал снимок по всему рабочему пространству, видел
задачи импорта коллег, отменял их и запускал применение чужой
подготовленной задачи. Своё задание при этом не ограничивало цели — в
YAML можно было назвать чужую карточку по ИНН, названию или UUID.

Проверки идут через HTTP; очередь, хранилище и внешние вызовы заменены
записывающими заглушками.
"""
from __future__ import annotations

import uuid

import pytest

import app.main  # noqa: F401
from tests.conftest import POSTGRES_AVAILABLE
from tests.test_sec01_lead_scoped_access import _lead, _user, call

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires PostgreSQL")


def _no_celery():
    """Контекст, в котором постановка в очередь записывается, а не уходит."""
    from app.scheduled.celery_app import celery_app

    sent: list = []
    orig = celery_app.send_task

    class _Ctx:
        def __enter__(self_inner):
            celery_app.send_task = lambda *a, **kw: sent.append((a, kw))
            return sent

        def __exit__(self_inner, *exc):
            celery_app.send_task = orig
            return False

    return _Ctx()


async def _import_job(db, workspace_id, user_id, *, status="previewed", diff=None):
    from app.import_export.models import ImportJob

    job = ImportJob(
        workspace_id=workspace_id,
        user_id=user_id,
        status=status,
        format="csv",
        source_filename="файл.csv",
        upload_size_bytes=100,
        total_rows=1,
        diff_json=diff,
    )
    db.add(job)
    await db.flush()
    return job


# ---------------------------------------------------------------------------
# Снимок
# ---------------------------------------------------------------------------


@skip_no_pg
@pytest.mark.asyncio
async def test_snapshot_gives_a_manager_only_their_own_leads(db, workspace):
    owner = await _user(db, workspace.id, "manager", "Owner")
    peer = await _user(db, workspace.id, "manager", "Peer")
    mine = await _lead(db, workspace.id, owner.id, "Моя компания")
    theirs = await _lead(db, workspace.id, peer.id, "Компания коллеги")

    res = await call(db, owner, "GET", "/api/export/snapshot")
    assert res.status_code == 200
    assert "Моя компания" in res.text
    assert "Компания коллеги" not in res.text
    assert str(theirs.id) not in res.text
    assert str(mine.id) in res.text


@skip_no_pg
@pytest.mark.asyncio
async def test_snapshot_filters_cannot_widen_a_managers_rights(db, workspace):
    owner = await _user(db, workspace.id, "manager", "Owner")
    peer = await _user(db, workspace.id, "manager", "Peer")
    await _lead(db, workspace.id, peer.id, "Компания коллеги")
    await _lead(db, workspace.id, None, "В базе лидов")

    # Чужой исполнитель — отказ, а не более широкая выборка.
    res = await call(db, owner, "GET", f"/api/export/snapshot?assigned_to={peer.id}")
    assert res.status_code == 403
    # База лидов менеджеру закрыта и здесь.
    res = await call(db, owner, "GET", "/api/export/snapshot?assignment_status=pool")
    assert res.status_code == 403


@skip_no_pg
@pytest.mark.asyncio
async def test_snapshot_gives_the_head_the_whole_workspace(db, workspace):
    head = await _user(db, workspace.id, "head", "Head")
    peer = await _user(db, workspace.id, "manager", "Peer")
    await _lead(db, workspace.id, peer.id, "Компания коллеги")

    res = await call(db, head, "GET", "/api/export/snapshot")
    assert res.status_code == 200
    assert "Компания коллеги" in res.text


@skip_no_pg
@pytest.mark.asyncio
async def test_snapshot_never_crosses_a_workspace(db, workspace):
    from app.auth.models import Workspace

    head = await _user(db, workspace.id, "head", "Head")
    await _lead(db, workspace.id, None, "Наша компания")

    other = Workspace(name="Other WS", plan="free")
    db.add(other)
    await db.flush()
    outsider = await _user(db, other.id, "admin", "Outsider")

    res = await call(db, outsider, "GET", "/api/export/snapshot")
    assert res.status_code == 200
    assert "Наша компания" not in res.text


# ---------------------------------------------------------------------------
# Задачи импорта
# ---------------------------------------------------------------------------


@skip_no_pg
@pytest.mark.asyncio
async def test_a_manager_sees_only_their_own_import_jobs(db, workspace):
    owner = await _user(db, workspace.id, "manager", "Owner")
    stranger = await _user(db, workspace.id, "manager", "Stranger")
    head = await _user(db, workspace.id, "head", "Head")

    theirs = await _import_job(db, workspace.id, owner.id)
    mine = await _import_job(db, workspace.id, stranger.id)

    res = await call(db, stranger, "GET", "/api/import/jobs")
    assert res.status_code == 200
    body = res.json()
    ids = {i["id"] for i in body["items"]}
    assert ids == {str(mine.id)}
    # total считается по той же выборке, иначе выдавал бы чужие задачи.
    assert body["total"] == 1

    head_res = await call(db, head, "GET", "/api/import/jobs")
    assert {i["id"] for i in head_res.json()["items"]} == {str(theirs.id), str(mine.id)}
    assert head_res.json()["total"] == 2


@skip_no_pg
@pytest.mark.asyncio
async def test_a_manager_cannot_touch_a_colleagues_import_job(db, workspace):
    owner = await _user(db, workspace.id, "manager", "Owner")
    stranger = await _user(db, workspace.id, "manager", "Stranger")
    job = await _import_job(db, workspace.id, owner.id, status="uploaded")

    with _no_celery() as sent:
        for method, path, body in (
            ("GET", f"/api/import/jobs/{job.id}", None),
            ("POST", f"/api/import/jobs/{job.id}/cancel", None),
            ("POST", f"/api/import/jobs/{job.id}/apply", None),
            ("POST", f"/api/import/jobs/{job.id}/confirm-mapping",
             {"mapping": {"A": "company_name"}}),
        ):
            res = await call(db, stranger, method, path, body)
            assert res.status_code == 404, (method, res.status_code)
            assert "файл.csv" not in res.text
        # Проверка владения идёт ДО постановки в очередь.
        assert sent == [], sent

    await db.refresh(job)
    assert job.status == "uploaded", "статус не должен был измениться"


@skip_no_pg
@pytest.mark.asyncio
async def test_the_owner_and_the_head_still_work_with_the_job(db, workspace):
    owner = await _user(db, workspace.id, "manager", "Owner")
    head = await _user(db, workspace.id, "head", "Head")
    job = await _import_job(db, workspace.id, owner.id)

    assert (await call(db, owner, "GET", f"/api/import/jobs/{job.id}")).status_code == 200
    assert (await call(db, head, "GET", f"/api/import/jobs/{job.id}")).status_code == 200

    with _no_celery() as sent:
        applied = await call(db, owner, "POST", f"/api/import/jobs/{job.id}/apply")
        assert applied.status_code == 202, applied.text[:200]
        assert len(sent) == 1


@skip_no_pg
@pytest.mark.asyncio
async def test_an_import_job_from_another_workspace_is_404(db, workspace):
    from app.auth.models import Workspace

    owner = await _user(db, workspace.id, "head", "Head")
    job = await _import_job(db, workspace.id, owner.id)

    other = Workspace(name="Other WS", plan="free")
    db.add(other)
    await db.flush()
    outsider = await _user(db, other.id, "admin", "Outsider")

    assert (
        await call(db, outsider, "GET", f"/api/import/jobs/{job.id}")
    ).status_code == 404
    assert (await call(db, outsider, "GET", "/api/import/jobs")).json()["total"] == 0


# ---------------------------------------------------------------------------
# Своё задание не даёт прав на чужие карточки
# ---------------------------------------------------------------------------


@skip_no_pg
@pytest.mark.asyncio
async def test_bulk_update_cannot_target_a_colleagues_lead(db, workspace):
    """Цель ищется по ИНН, названию и UUID — закрыты все три пути."""
    from app.import_export.diff_engine import compute_diff

    owner = await _user(db, workspace.id, "manager", "Owner")
    peer = await _user(db, workspace.id, "manager", "Peer")
    theirs = await _lead(db, workspace.id, peer.id, "Компания коллеги")
    theirs.inn = "7700000001"
    mine = await _lead(db, workspace.id, owner.id, "Моя компания")
    mine.inn = "7700000002"
    await db.flush()

    updates = [
        {"action": "update", "match_by": "id",
         "company": {"id": str(theirs.id), "city": "Казань"}},
        {"action": "update", "match_by": "inn",
         "company": {"inn": "7700000001", "city": "Казань"}},
        {"action": "update", "match_by": "company_name",
         "company": {"name": "Компания коллеги", "city": "Казань"}},
        {"action": "update", "match_by": "id",
         "company": {"id": str(mine.id), "city": "Казань"}},
    ]
    diff = await compute_diff(
        db, workspace_id=workspace.id, updates=updates, actor=owner
    )

    foreign, own = diff[:3], diff[3]
    for item in foreign:
        assert item.error, item
        assert item.lead_id is None
        # Текст тот же, что у ненайденной: существование чужой карточки
        # подтверждать незачем.
        assert item.error == "Лид не найден"
    assert own.error is None and own.lead_id == str(mine.id)

    # Руководителю те же цели доступны.
    head = await _user(db, workspace.id, "head", "Head")
    head_diff = await compute_diff(
        db, workspace_id=workspace.id, updates=updates[:1], actor=head
    )
    assert head_diff[0].error is None


@skip_no_pg
@pytest.mark.asyncio
async def test_the_worker_rechecks_targets_before_writing(db, workspace):
    """`diff_json` собран раньше и мог устареть — на записи проверяем снова."""
    from app.scheduled import jobs as jobs_mod

    owner = await _user(db, workspace.id, "manager", "Owner")
    peer = await _user(db, workspace.id, "manager", "Peer")
    theirs = await _lead(db, workspace.id, peer.id, "Компания коллеги")

    # Задание, в котором цель уже проставлена: так выглядел бы разбор,
    # сделанный до передачи карточки другому менеджеру.
    diff = {
        "type": "bulk_update",
        "items": [
            {
                "action": "update",
                "company_name": "Компания коллеги",
                "inn": None,
                "lead_id": str(theirs.id),
                "changes": [{"field": "city", "before": None, "after": "Казань"}],
                "error": None,
                "match_confidence": "high",
            }
        ],
        "stats": {"to_update": 1, "to_create": 0, "errors": 0},
    }
    job = await _import_job(db, workspace.id, owner.id, status="previewed", diff=diff)

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
        result = await jobs_mod._run_bulk_update(job.id)
    finally:
        jobs_mod._build_task_engine_and_factory = orig

    await db.refresh(theirs)
    assert theirs.city is None, "чужая карточка не должна была измениться"
    await db.refresh(job)
    assert job.failed == 1 and job.succeeded == 0, (job.failed, job.succeeded, result)
