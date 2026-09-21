"""DATA-01 (P2-11): валидация assignment_status на путях селекции.

`LeadSelection.assignment_status` принимает от вызывающего произвольную
строку без проверки (`selection.py::from_query/from_params`,
`__post_init__` её не трогает). Реальный набор значений, которые пишет
код — `pool`, `assigned` (`app/leads/models.py::AssignmentStatus` также
объявляет `transferred`, но никто его не пишет), плюс `deleted`, который
фронтенд пишет напрямую через `PATCH /leads/{id}` для отклонения
auto-created карточек (`NeedsReviewRow.tsx`) — в модели он не объявлен,
но это тоже легитимное значение.

Воспроизведение (`DATA-01/REPRO.md`) показало: пути, реально принимающие
`assignment_status` от вызывающего, — `POST /api/export` (`filters`) и
`GET /api/export/snapshot` (query) — для руководителя/админа неизвестное
значение проходит без проверки и превращается в пустую выборку (не
расширенную и без 500). Для менеджера уже есть отдельная проверка
`!= "assigned"` → 403 (`app/import_export/access.py`), поэтому там
контрпример не воспроизводится.

`GET /leads/pool` и `POST /leads/assign` этот параметр от вызывающего не
берут вовсе (сервер сам подставляет `"pool"`), так что они не являются
путями инъекции и не тестируются здесь.

Отдельно найден `PATCH /leads/{id}` (`LeadUpdate.assignment_status`,
`app/leads/services.py::update_lead`) — этот путь не идёт через
`LeadSelection`, а пишет присланную строку в колонку `leads.assignment_status`
без всякой проверки. Это не «путь селекции» в терминах контракта, но
`app/leads/schemas.py` явно в allowlist контракта, и это самый опасный из
найденных путей (порча инварианта pool/assigned/deleted, а не просто
лишний фильтр в выдаче) — вынесен отдельным тестом с явной пометкой.
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


async def _export(db, actor, filters: dict):
    from app.scheduled.celery_app import celery_app

    orig = celery_app.send_task
    celery_app.send_task = lambda *a, **kw: None
    try:
        return await _call(
            db, actor, "POST", "/api/export",
            json={"format": "csv", "filters": filters, "include_ai_brief": False},
        )
    finally:
        celery_app.send_task = orig


# ---------------------------------------------------------------------------
# ASSIGN-01 — допустимые значения работают как раньше
# ---------------------------------------------------------------------------

@skip_no_pg
async def test_assign01_omitted_defaults_to_pool_scope(db, workspace):
    """GET /leads/pool без assignment_status — прежнее поведение: пул."""
    head = await _user(db, workspace.id, "head", "Head")
    await _lead(db, workspace.id, name="Пул Ко", pool=True)
    await _lead(db, workspace.id, name="Чужая Ко", assigned_to=head.id)
    await db.commit()

    r = await _call(db, head, "GET", "/leads/pool")
    assert r.status_code == 200
    body = r.json()
    names = {item["company_name"] for item in body["items"]}
    assert names == {"Пул Ко"}


@skip_no_pg
async def test_assign01_known_values_still_work_on_export(db, workspace):
    """`assigned` и `pool` в фильтре экспорта — как раньше, без изменений."""
    head = await _user(db, workspace.id, "head", "Head")
    manager = await _user(db, workspace.id, "manager", "Manager")
    await _lead(db, workspace.id, name="Пул Ко", pool=True)
    await _lead(db, workspace.id, name="Моя Ко", assigned_to=manager.id)
    await db.commit()

    r = await _export(db, head, {"assignment_status": "pool"})
    assert r.status_code == 202, r.text

    r = await _export(db, head, {"assignment_status": "assigned"})
    assert r.status_code == 202, r.text


@skip_no_pg
async def test_assign01_deleted_still_accepted_via_patch(db, workspace):
    """`deleted` — реальное значение, которым фронтенд отклоняет
    auto-created карточку (NeedsReviewRow.tsx). Фикс не должен его сломать."""
    manager = await _user(db, workspace.id, "manager", "Manager")
    lead = await _lead(db, workspace.id, name="Авто Ко", assigned_to=manager.id)
    await db.commit()

    r = await _call(db, manager, "PATCH", f"/leads/{lead.id}", json={"assignment_status": "deleted"})
    assert r.status_code == 200, r.text
    assert r.json()["assignment_status"] == "deleted"


# ---------------------------------------------------------------------------
# ASSIGN-02 — неизвестное значение → контрактная 4xx, не 500 и не расширение
# ---------------------------------------------------------------------------

@skip_no_pg
async def test_assign02_unknown_value_rejected_on_export_create(db, workspace):
    """POST /api/export, filters.assignment_status=zzz, руководитель.

    Сейчас (до фикса): 202, задача создаётся с filters_json содержащим
    'zzz' — не 500, но и не отказ. Ожидаемый контракт — 4xx.
    """
    head = await _user(db, workspace.id, "head", "Head")
    await _lead(db, workspace.id, name="Пул Ко", pool=True)
    await db.commit()

    r = await _export(db, head, {"assignment_status": "zzz"})
    assert r.status_code in (400, 422), (
        f"ожидали контрактную 4xx на неизвестное assignment_status, "
        f"получили {r.status_code}: {r.text}"
    )


@skip_no_pg
async def test_assign02_unknown_value_rejected_on_snapshot(db, workspace):
    """GET /api/export/snapshot?assignment_status=zzz, руководитель.

    Сейчас (до фикса): 200 с пустым leads: [] — не расширение, но и не
    отказ. Ожидаемый контракт — 4xx.
    """
    head = await _user(db, workspace.id, "head", "Head")
    await _lead(db, workspace.id, name="Пул Ко", pool=True)
    await db.commit()

    r = await _call(db, head, "GET", "/api/export/snapshot?assignment_status=zzz")
    assert r.status_code in (400, 422), (
        f"ожидали контрактную 4xx на неизвестное assignment_status, "
        f"получили {r.status_code}: {r.text}"
    )


@skip_no_pg
async def test_assign02_unknown_value_never_expands_selection_for_manager(db, workspace):
    """Контрольная точка: у менеджера неизвестное значение и так уже
    отклоняется (`!= "assigned"` в access.py) — фиксируем, что фикс не
    должен эту защиту ослабить."""
    manager = await _user(db, workspace.id, "manager", "Manager")
    await _lead(db, workspace.id, name="Пул Ко", pool=True)
    await db.commit()

    r = await _export(db, manager, {"assignment_status": "zzz"})
    assert r.status_code == 403, r.text

    r = await _call(db, manager, "GET", "/api/export/snapshot?assignment_status=zzz")
    assert r.status_code == 403, r.text


@skip_no_pg
async def test_assign02_write_path_patch_rejects_unknown_value(db, workspace):
    """НЕ путь селекции, но тот же allowlist (app/leads/schemas.py) и тот
    же корень (assignment_status без единого набора допустимых значений).

    Сейчас (до фикса): 200, 'zzz' пишется в колонку как есть — порча
    инварианта pool/assigned/deleted, используемого во всём приложении
    (team/company агрегаты, `Lead.assignment_status == 'assigned'` и
    т.п.). Severity здесь выше, чем у путей селекции: не лишний фильтр в
    выдаче, а порча данных лида.
    """
    manager = await _user(db, workspace.id, "manager", "Manager")
    lead = await _lead(db, workspace.id, name="Моя Ко", assigned_to=manager.id)
    await db.commit()

    r = await _call(db, manager, "PATCH", f"/leads/{lead.id}", json={"assignment_status": "zzz"})
    assert r.status_code in (400, 422), (
        f"ожидали контрактную 4xx на неизвестное assignment_status в PATCH, "
        f"получили {r.status_code}: {r.text}"
    )
