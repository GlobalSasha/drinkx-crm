"""Разведка SEC-01: что на самом деле отвечают lead-scoped маршруты.

Не тест: печатает таблицу. Отсутствие зависимости на роутере ещё не значит
«уязвим» — обработчик может сузить выборку сам. Здесь каждый маршрут
реально вызывается от лица менеджера, которому этот лид не принадлежит, и
записывается код ответа.

    REQUIRE_TEST_DB=1 python -m pytest tests/recon_sec01_lead_scoped.py -q -s

Как читать коды:

* 403/404 — что-то защитило, надо смотреть что именно;
* 422 — зависимости пропустили, упала только валидация тела: защиты нет,
  нужен корректный запрос, чтобы увидеть последствия;
* 2xx — выполнилось: для GET это утечка, для записи — изменение чужого лида;
* 500 — смотреть отдельно.
"""
from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

import app.main  # noqa: F401
from tests.conftest import POSTGRES_AVAILABLE

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires PostgreSQL")


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


async def _lead(db, workspace_id, owner_id, name="Чужая компания"):
    from app.leads import repositories as repo

    return await repo.create_lead(
        db, workspace_id, dict(company_name=name),
        assigned_to=owner_id, assignment_status="assigned",
    )


async def _call(db, actor, method, path, body=None):
    from app.auth.dependencies import current_user
    from app.db import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[current_user] = lambda: actor
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            kwargs = {}
            if method in ("POST", "PATCH", "PUT"):
                kwargs["json"] = body if body is not None else {}
            return await c.request(method, path, **kwargs)
    finally:
        app.dependency_overrides.clear()


def _routes():
    """Все маршруты с {lead_id} и признак «есть ли страж на роутере»."""
    from fastapi.routing import APIRoute

    from app.main import app

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

    rows = []
    for r in app.routes:
        if not isinstance(r, APIRoute):
            continue
        if "{lead_id}" not in r.path or r.path.startswith("/external"):
            continue
        n = names(r)
        for method in sorted(r.methods - {"HEAD", "OPTIONS"}):
            rows.append(
                {
                    "path": r.path,
                    "method": method,
                    "guard": "lead_access_guard" in n,
                    "role": any("admin_or_head" in x for x in n),
                }
            )
    rows.sort(key=lambda x: (x["path"], x["method"]))
    return rows


async def _fresh(db, workspace, owner):
    """Свежий чужой лид с дочерними объектами — на каждый маршрут свой.

    Иначе пишущие маршруты рушат состояние: `DELETE /leads/{id}` от
    владельца удаляет карточку, и все последующие проверки отвечают 404
    не потому, что защищены.
    """
    from app.activity.models import Activity, ActivityType
    from app.contacts.models import Contact
    from app.followups.models import Followup

    lead = await _lead(db, workspace.id, owner.id)
    task = Activity(
        workspace_id=None, lead_id=lead.id, user_id=owner.id,
        type=ActivityType.task.value, payload_json={"title": "Секрет"},
        body="Секрет", task_done=False,
    )
    contact = Contact(workspace_id=workspace.id, lead_id=lead.id, name="ЛПР Чужой")
    followup = Followup(
        lead_id=lead.id, name="Перезвонить", reminder_kind="manager", status="pending"
    )
    for row in (task, contact, followup):
        db.add(row)
    await db.flush()
    return lead, {
        "{activity_id}": str(task.id),
        "{task_id}": str(task.id),
        "{contact_id}": str(contact.id),
        "{fu_id}": str(followup.id),
        "{note_id}": str(uuid.uuid4()),
        "{quote_id}": str(uuid.uuid4()),
    }


async def _probe(db, actor, method, path):
    try:
        return str((await _call(db, actor, method, path)).status_code)
    except Exception as exc:  # noqa: BLE001 — разведка не должна падать
        return f"EXC:{type(exc).__name__}"


@skip_no_pg
@pytest.mark.asyncio
async def test_recon(db, workspace):
    import logging

    # httpx печатает строку на каждый запрос — таблицу не прочитать.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    owner = await _user(db, workspace.id, "manager", "Owner")
    stranger = await _user(db, workspace.id, "manager", "Stranger")
    head = await _user(db, workspace.id, "head", "Head")

    results = []
    for r in _routes():
        lead, subs = await _fresh(db, workspace, owner)
        path = r["path"].replace("{lead_id}", str(lead.id))
        for token, value in subs.items():
            path = path.replace(token, value)
        # Чужой первым: он не должен ничего изменить, и порядок это
        # подтверждает — владелец после него видит карточку живой.
        stranger_code = await _probe(db, stranger, r["method"], path)
        owner_code = await _probe(db, owner, r["method"], path)

        lead2, subs2 = await _fresh(db, workspace, owner)
        path2 = r["path"].replace("{lead_id}", str(lead2.id))
        for token, value in subs2.items():
            path2 = path2.replace(token, value)
        head_code = await _probe(db, head, r["method"], path2)

        results.append({**r, "stranger": stranger_code, "owner": owner_code, "head": head_code})

    print(f"\n{'МАРШРУТ':50} {'МЕТОД':7} {'СТРАЖ':6} {'ЧУЖОЙ':7} {'СВОЙ':6} {'HEAD':6}")
    print("-" * 92)
    for r in results:
        mark = "GUARD" if r["guard"] else ("ROLE" if r["role"] else "—")
        short = r["path"].replace("/leads/{lead_id}", "…").replace("/api/leads/{lead_id}", "/api…")
        print(f"{short:50} {r['method']:7} {mark:6} {r['stranger']:7} {r['owner']:6} {r['head']:6}")

    leaks = [
        r for r in results
        if r["stranger"] == r["owner"] and not r["stranger"].startswith(("401", "403", "404", "EXC"))
    ]
    print("\n=== ЧУЖОМУ ОТВЕТИЛИ ТАК ЖЕ, КАК ВЛАДЕЛЬЦУ (не отказ) ===")
    for r in leaks:
        print(f"  {r['method']:7} {r['path']:52} → {r['stranger']}")
    print(f"\nмаршрутов всего: {len(results)}, требуют разбора: {len(leaks)}")

    validation_only = [
        r for r in results
        if r["stranger"].startswith("422") and not r["guard"]
    ]
    print("\n=== ЧУЖОГО ОСТАНОВИЛА ТОЛЬКО ВАЛИДАЦИЯ ТЕЛА (защиты нет) ===")
    for r in validation_only:
        print(f"  {r['method']:7} {r['path']}")
    print(f"всего: {len(validation_only)}")
