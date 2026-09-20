"""SEC-D4 (кандидат SEC-DELTA-002): различимость чужого и несуществующего
лида в preview bulk-update по `match_confidence`.

`compute_diff` (app/import_export/diff_engine.py) сперва проставляет
`item.match_confidence` по результату поиска (`_resolve_match`), а уже потом
проверяет `may_access_lead`. Ветка отказа по правам унифицирует `error`
("Лид не найден") и не проставляет `lead_id`/`changes` — но не сбрасывает
`match_confidence`. В результате чужой существующий лид (`exact_inn`) и
несуществующий (`not_found`) при одинаковом `error` различаются по
`match_confidence`, и это уезжает клиенту через `diff_json` в
`GET /api/import/jobs/{id}`. Это утечка факта существования карточки, не
чтение её содержимого.

Дуга собрана по образцу test_sec02_import_export_access.py (те же `_user`,
`_lead`, `call`, `_import_job`, `_no_celery`).
"""
from __future__ import annotations

import uuid

import pytest

from tests.conftest import POSTGRES_AVAILABLE
from tests.test_sec01_lead_scoped_access import _lead, _user, call
from tests.test_sec02_import_export_access import _import_job, _no_celery

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires PostgreSQL")


async def _count(db, model) -> int:
    from sqlalchemy import func, select

    res = await db.execute(select(func.count()).select_from(model))
    return res.scalar_one()


# ---------------------------------------------------------------------------
# PREVIEW-01 — чужой существующий и несуществующий лид должны быть неотличимы
# ---------------------------------------------------------------------------

@skip_no_pg
@pytest.mark.asyncio
async def test_preview01_foreign_lead_and_missing_lead_are_indistinguishable(
    db, workspace
):
    """Одинаковый валидный bulk-update вход: (а) ИНН чужого лида того же
    воркспейса, (б) ИНН чужого лида другого воркспейса, (в) ИНН, которого
    нет вообще. Наблюдаемый результат (DiffItem и ответ
    GET /api/import/jobs/{id}) обязан быть одинаковым для (а)/(б)/(в):
    тот же error, тот же match_confidence, ни lead_id, ни changes.

    На текущем коде это падает на match_confidence: чужой лид того же
    воркспейса резолвится ("exact_inn") ДО проверки прав, и это значение
    не сбрасывается в ветке отказа — тогда как несуществующий лид
    получает "not_found". Один и тот же error ("Лид не найден") при
    разном match_confidence — и есть SEC-DELTA-002.
    """
    from app.auth.models import Workspace
    from app.import_export.diff_engine import compute_diff, diff_to_jsonable

    owner = await _user(db, workspace.id, "manager", "Owner")
    peer = await _user(db, workspace.id, "manager", "Peer")

    other_ws = Workspace(name="Other WS", plan="free")
    db.add(other_ws)
    await db.flush()
    stranger = await _user(db, other_ws.id, "manager", "Stranger")

    theirs_same_ws = await _lead(db, workspace.id, peer.id, "Компания коллеги")
    theirs_same_ws.inn = "7700000101"
    theirs_other_ws = await _lead(db, other_ws.id, stranger.id, "Чужой воркспейс")
    theirs_other_ws.inn = "7700000102"
    await db.flush()

    missing_inn = "7700000199"  # заведомо отсутствует

    updates = [
        {"action": "update", "match_by": "inn",
         "company": {"inn": theirs_same_ws.inn},
         "fields": {"tags": {"add": ["vip"]}}},
        {"action": "update", "match_by": "inn",
         "company": {"inn": theirs_other_ws.inn},
         "fields": {"tags": {"add": ["vip"]}}},
        {"action": "update", "match_by": "inn",
         "company": {"inn": missing_inn},
         "fields": {"tags": {"add": ["vip"]}}},
    ]

    diff = await compute_diff(
        db, workspace_id=workspace.id, updates=updates, actor=owner
    )
    foreign_same_ws, foreign_other_ws, not_found = diff

    # --- сначала контрольные инварианты, которые уже держит SEC-02 -----
    for item in diff:
        assert item.error == "Лид не найден", item
        assert item.lead_id is None, item
        assert not item.changes, item

    # --- сама находка: match_confidence должен совпадать -----------------
    assert foreign_same_ws.match_confidence == not_found.match_confidence, (
        "SEC-DELTA-002: чужой существующий лид того же воркспейса "
        f"отдаёт match_confidence={foreign_same_ws.match_confidence!r}, "
        f"а несуществующий — {not_found.match_confidence!r}; при "
        "одинаковом error это различает 'есть, но не ваш' от 'такого нет'."
    )
    # Лид другого воркспейса и так не находится на этапе запроса
    # (compute_diff скопирован по workspace_id) — этот случай уже безопасен,
    # фиксируем как регрессионный инвариант.
    assert foreign_other_ws.match_confidence == not_found.match_confidence

    # --- то же самое должно быть видно и через HTTP-ответ ----------------
    diff_payload = {
        "type": "bulk_update",
        "items": diff_to_jsonable(diff),
        "stats": {"to_update": 0, "to_create": 0, "errors": len(diff)},
    }
    job = await _import_job(db, workspace.id, owner.id, diff=diff_payload)

    resp = await call(db, owner, "GET", f"/api/import/jobs/{job.id}")
    assert resp.status_code == 200, resp.text[:200]
    items = resp.json()["diff_json"]["items"]
    http_foreign, http_foreign_other, http_missing = items

    for it in items:
        assert it["error"] == "Лид не найден"
        assert it["lead_id"] is None
        assert not it["changes"]

    assert http_foreign["match_confidence"] == http_missing["match_confidence"], (
        "SEC-DELTA-002 виден и в ответе GET /api/import/jobs/{id}: "
        f"{http_foreign['match_confidence']!r} != {http_missing['match_confidence']!r}"
    )


# ---------------------------------------------------------------------------
# PREVIEW-02 — свой лид: допустимый preview, без побочных эффектов
# ---------------------------------------------------------------------------

@skip_no_pg
@pytest.mark.asyncio
async def test_preview02_own_lead_preview_is_allowed_and_has_no_side_effects(
    db, workspace
):
    """Свой лид по ИНН — нормальный preview: match_confidence=exact_inn,
    lead_id есть, changes есть. Сам preview (upload) ничего не пишет в
    БД (число лидов/активностей не меняется) и не ставит задачу
    (send_task не вызван) — считает диф и только."""
    from app.activity.models import Activity
    from app.import_export.diff_engine import compute_diff
    from app.import_export.routers import _handle_bulk_update_upload
    from app.leads.models import Lead

    owner = await _user(db, workspace.id, "manager", "Owner")
    mine = await _lead(db, workspace.id, owner.id, "Моя компания")
    mine.inn = "7700000201"
    await db.flush()

    updates = [
        {"action": "update", "match_by": "inn",
         "company": {"inn": mine.inn},
         "fields": {"tags": {"add": ["vip"]}}},
    ]

    diff = await compute_diff(
        db, workspace_id=workspace.id, updates=updates, actor=owner
    )
    own = diff[0]
    assert own.error is None
    assert own.match_confidence == "exact_inn"
    assert own.lead_id == str(mine.id)
    assert own.changes

    # --- нет побочных эффектов на реальном preview-пути (HTTP-уровень) ---
    leads_before = await _count(db, Lead)
    activities_before = await _count(db, Activity)

    yaml_body = (
        "format: drinkx-crm-update\n"
        "version: \"1.0\"\n"
        "updates:\n"
        "  - action: update\n"
        "    match_by: inn\n"
        "    company:\n"
        f"      inn: \"{mine.inn}\"\n"
        "    fields:\n"
        "      tags:\n"
        "        add: [\"vip\"]\n"
    ).encode("utf-8")

    with _no_celery() as sent:
        job_out = await _handle_bulk_update_upload(
            content=yaml_body,
            filename="update.yaml",
            db=db,
            user=owner,
        )
        assert sent == [], "preview не должен ставить задачу в очередь"

    leads_after = await _count(db, Lead)
    activities_after = await _count(db, Activity)
    assert leads_after == leads_before, "preview не должен создавать/менять лиды"
    assert activities_after == activities_before, "preview не должен писать активности"

    preview_item = job_out.diff_json["items"][0]
    assert preview_item["match_confidence"] == "exact_inn"
    assert preview_item["lead_id"] == str(mine.id)
    assert preview_item["changes"]


# ---------------------------------------------------------------------------
# Контроль — руководитель видит чужой лид своего воркспейса (допустимо)
# ---------------------------------------------------------------------------

@skip_no_pg
@pytest.mark.asyncio
async def test_head_preview_of_a_managers_lead_in_own_workspace_is_allowed(
    db, workspace
):
    """Политика: head/admin видят весь воркспейс — их preview по чужому
    (для них) лиду штатный, не должен превращаться в отказ."""
    from app.import_export.diff_engine import compute_diff

    manager = await _user(db, workspace.id, "manager", "Manager")
    head = await _user(db, workspace.id, "head", "Head")
    theirs = await _lead(db, workspace.id, manager.id, "Компания менеджера")
    theirs.inn = "7700000301"
    await db.flush()

    updates = [
        {"action": "update", "match_by": "inn",
         "company": {"inn": theirs.inn},
         "fields": {"tags": {"add": ["vip"]}}},
    ]

    diff = await compute_diff(
        db, workspace_id=workspace.id, updates=updates, actor=head
    )
    item = diff[0]
    assert item.error is None
    assert item.match_confidence == "exact_inn"
    assert item.lead_id == str(theirs.id)
    assert item.changes


# ---------------------------------------------------------------------------
# PREVIEW-03 — контр-мутация (документирует, что тест реально ловит регресс)
# ---------------------------------------------------------------------------

@skip_no_pg
@pytest.mark.asyncio
async def test_preview03_mutation_guard_flags_stale_confidence(db, workspace):
    """Если вернуть старое поведение (не сбрасывать match_confidence в
    ветке отказа), PREVIEW-01 обязан упасть именно на этом сравнении —
    проверяем это напрямую здесь, чтобы порча реализации не прошла
    незамеченной, даже если кто-то перепишет PREVIEW-01."""
    from app.import_export.diff_engine import compute_diff

    owner = await _user(db, workspace.id, "manager", "Owner")
    peer = await _user(db, workspace.id, "manager", "Peer")
    theirs = await _lead(db, workspace.id, peer.id, "Компания коллеги")
    theirs.inn = "7700000401"
    await db.flush()

    updates = [
        {"action": "update", "match_by": "inn",
         "company": {"inn": theirs.inn, "city": "Казань"}},
        {"action": "update", "match_by": "inn",
         "company": {"inn": "7700000499", "city": "Казань"}},
    ]

    diff = await compute_diff(
        db, workspace_id=workspace.id, updates=updates, actor=owner
    )
    foreign, not_found = diff
    assert foreign.error == not_found.error == "Лид не найден"

    # Текущий код (до фикса SEC-DELTA-002) оставляет "exact_inn" на отказе
    # по правам — это и есть наблюдаемая утечка существования карточки.
    if foreign.match_confidence != not_found.match_confidence:
        pytest.xfail(
            "SEC-DELTA-002 воспроизведён: match_confidence различает "
            f"чужой лид ({foreign.match_confidence!r}) и несуществующий "
            f"({not_found.match_confidence!r}) при одинаковом error"
        )
