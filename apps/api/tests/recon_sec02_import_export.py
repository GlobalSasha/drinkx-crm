"""Разведка SEC-02: права на import/export.

Не тест: печатает таблицу. Экспорт лидов уже закрыт (`622b107`), здесь —
всё остальное: снимок, задачи импорта, их отмена и применение.

    REQUIRE_TEST_DB=1 python -m pytest tests/recon_sec02_import_export.py -q -s
"""
from __future__ import annotations

import logging
import uuid

import pytest

import app.main  # noqa: F401
from tests.conftest import POSTGRES_AVAILABLE
from tests.recon_sec01_lead_scoped import _call, _lead, _user

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires PostgreSQL")


def _guards():
    """Какие зависимости стоят на маршрутах import/export."""
    from fastapi.routing import APIRoute

    from app.main import app

    rows = []
    for r in app.routes:
        if not isinstance(r, APIRoute):
            continue
        if not r.path.startswith(("/api/import", "/api/export")):
            continue
        names = []

        def walk(d):
            n = getattr(d.call, "__name__", None)
            if n:
                names.append(n)
            for s in d.dependencies:
                walk(s)

        walk(r.dependant)
        role = "admin_or_head" if any("admin_or_head" in n for n in names) else "—"
        for m in sorted(r.methods - {"HEAD", "OPTIONS"}):
            rows.append((r.path, m, role))
    rows.sort()
    return rows


@skip_no_pg
@pytest.mark.asyncio
async def test_recon(db, workspace):
    logging.getLogger("httpx").setLevel(logging.WARNING)

    print("\n--- какие роли требуют маршруты import/export ---")
    for path, method, role in _guards():
        print(f"  {method:7} {path:42} роль: {role}")

    from app.import_export.models import ImportJob

    owner = await _user(db, workspace.id, "manager", "Owner")
    stranger = await _user(db, workspace.id, "manager", "Stranger")
    head = await _user(db, workspace.id, "head", "Head")

    # Чужая задача импорта: заведена другим менеджером.
    job = ImportJob(
        workspace_id=workspace.id,
        user_id=owner.id,
        status="previewed",
        format="csv",
        source_filename="чужой-файл.csv",
        upload_size_bytes=100,
        total_rows=3,
    )
    db.add(job)
    await db.flush()

    # Лид владельца — проверяем, может ли импорт чужого тронуть его.
    lead = await _lead(db, workspace.id, owner.id, name="Компания владельца")

    print("\n--- задача импорта, заведённая ДРУГИМ менеджером ---")
    for actor, label in ((stranger, "чужой менеджер"), (head, "руководитель")):
        listed = await _call(db, actor, "GET", "/api/import/jobs")
        body = listed.json() if listed.status_code == 200 else {}
        visible = len(body.get("items", []))
        got = await _call(db, actor, "GET", f"/api/import/jobs/{job.id}")
        print(f"  {label:18} список: {listed.status_code} видит задач: {visible}"
              f"   чтение чужой: {got.status_code}")

    cancelled = await _call(db, stranger, "POST", f"/api/import/jobs/{job.id}/cancel")
    print(f"  чужой менеджер отменяет чужую задачу: {cancelled.status_code}")
    await db.refresh(job)
    print(f"  статус задачи после этого: {job.status!r}")

    # Применение чужой задачи: именно оно создаёт и правит карточки.
    job2 = ImportJob(
        workspace_id=workspace.id, user_id=owner.id, status="previewed",
        format="csv", source_filename="чужой.csv", upload_size_bytes=100,
        total_rows=1,
        diff_json={"rows": [{"company_name": "Из чужого импорта"}]},
    )
    db.add(job2)
    await db.flush()
    from app.scheduled.celery_app import celery_app

    orig = celery_app.send_task
    celery_app.send_task = lambda *a, **kw: None
    try:
        applied = await _call(db, stranger, "POST", f"/api/import/jobs/{job2.id}/apply")
    finally:
        celery_app.send_task = orig
    await db.refresh(job2)
    print(f"  чужой менеджер применяет чужую задачу: {applied.status_code}"
          f"  статус после: {job2.status!r}")

    confirmed = await _call(
        db, stranger, "POST", f"/api/import/jobs/{job.id}/confirm-mapping",
        {"mapping": {"A": "company_name"}},
    )
    print(f"  чужой менеджер меняет маппинг чужой задачи: {confirmed.status_code}")

    up = await _call(db, stranger, "POST", "/api/import/upload")
    print(f"  менеджер загружает файл импорта (без тела): {up.status_code}")

    print("\n--- снимок и подсказка ---")
    for actor, label in ((stranger, "менеджер"), (head, "руководитель")):
        snap = await _call(db, actor, "GET", "/api/export/snapshot")
        size = len(snap.content) if snap.status_code == 200 else 0
        leads_in = 0
        if snap.status_code == 200:
            text = snap.text
            leads_in = text.count(lead.company_name)
        print(f"  {label:15} /export/snapshot: {snap.status_code}  байт: {size}"
              f"  упоминаний чужого лида: {leads_in}")
    prompt = await _call(db, stranger, "GET", "/api/export/bulk-update-prompt")
    print(f"  менеджер /export/bulk-update-prompt: {prompt.status_code}")
