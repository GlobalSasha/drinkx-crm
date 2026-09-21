"""QA-оракул UX-DELTA-003 — POST /leads/assign (mode="ids") отвечает 500 после commit.

Контракт: /private/tmp/.../scratchpad/program/contracts/UX-DELTA-003.md

Живой репро (стенд): руководитель на /leads-pool выдаёт карточку менеджеру,
web шлёт `POST /leads/assign {"mode": "ids", ...}`; после commit сериализация
`LeadAssignOut.items[*].updated_at` дёргает протухший ORM-атрибут
(`onupdate=func.now()` из TimestampedMixin) и падает `MissingGreenlet` — 500,
хотя данные в БД уже обновлены. `mode="filter"` не страдает: там ORM-объекты
приходят из `UPDATE ... RETURNING`, а не из ленивой послекоммитной догрузки.

Этот файл — независимый HTTP-оракул (единственный существующий HTTP-тест на
`mode="ids"` — до этого его вызывали только напрямую как сервис в
test_lead_assignment.py, поэтому дефект не ловился). Ожидание ДО фикса:
A1/A3 красные с 500/MissingGreenlet, A4 зелёный.
"""
from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

import app.main  # noqa: F401 — настраивает мапперы SQLAlchemy
from tests.conftest import POSTGRES_AVAILABLE

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires PostgreSQL")


# --- хелперы (те же паттерны, что test_lead_pool_selection.py / test_lead_assignment.py) ---

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


async def _lead(db, workspace_id, **kwargs):
    from app.leads import repositories as repo

    assignment_status = kwargs.pop("assignment_status", "pool")
    assigned_to = kwargs.pop("assigned_to", None)
    payload = dict(company_name=f"Company {uuid.uuid4().hex[:6]}")
    payload.update(kwargs)
    return await repo.create_lead(
        db,
        workspace_id,
        payload,
        assigned_to=assigned_to,
        assignment_status=assignment_status,
    )


async def call(db, actor, method: str, path: str, **kwargs):
    """Настоящий HTTP-запрос через ASGI-приложение: подменяются только
    сессия и текущий пользователь — как в test_lead_pool_selection.py:77."""
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


# ---------------------------------------------------------------------------
# A1 — HTTP mode=ids → 200, updated_at не null, assigned_to/assignment_status
# ---------------------------------------------------------------------------

@skip_no_pg
@pytest.mark.asyncio
async def test_a1_head_assigns_one_lead_by_ids_over_http(db, workspace):
    head = await _user(db, workspace.id, "head", "Head")
    manager = await _user(db, workspace.id, "manager", "Kirill")
    lead = await _lead(db, workspace.id)

    res = await call(
        db, head, "POST", "/leads/assign",
        json={
            "to_user_id": str(manager.id),
            "mode": "ids",
            "lead_ids": [str(lead.id)],
        },
    )

    assert res.status_code == 200, (
        "A1: HTTP mode=ids с 1 лидом должен вернуть 200. Фактический "
        f"ответ: {res.status_code} {res.text}"
    )
    body = res.json()
    assert body["assigned_count"] == 1, body
    item = body["items"][0]
    assert item["updated_at"] is not None, "A1: updated_at не должен быть null"
    assert item["assigned_to"] == str(manager.id)
    assert item["assignment_status"] == "assigned"


@skip_no_pg
@pytest.mark.asyncio
async def test_a1_head_assigns_two_leads_by_ids_over_http(db, workspace):
    head = await _user(db, workspace.id, "head", "Head")
    manager = await _user(db, workspace.id, "manager", "Kirill")
    leads = [await _lead(db, workspace.id) for _ in range(2)]

    res = await call(
        db, head, "POST", "/leads/assign",
        json={
            "to_user_id": str(manager.id),
            "mode": "ids",
            "lead_ids": [str(lead.id) for lead in leads],
        },
    )

    assert res.status_code == 200, (
        f"A1 (2 лида): ожидали 200, получили {res.status_code} {res.text}"
    )
    body = res.json()
    assert body["assigned_count"] == 2, body
    for item in body["items"]:
        assert item["updated_at"] is not None
        assert item["assigned_to"] == str(manager.id)
        assert item["assignment_status"] == "assigned"


@skip_no_pg
@pytest.mark.asyncio
async def test_a1_admin_assigns_lead_by_ids_over_http(db, workspace):
    admin = await _user(db, workspace.id, "admin", "Admin")
    manager = await _user(db, workspace.id, "manager", "Kirill")
    lead = await _lead(db, workspace.id)

    res = await call(
        db, admin, "POST", "/leads/assign",
        json={
            "to_user_id": str(manager.id),
            "mode": "ids",
            "lead_ids": [str(lead.id)],
        },
    )

    assert res.status_code == 200, (
        f"A1 (admin): ожидали 200, получили {res.status_code} {res.text}"
    )
    body = res.json()
    item = body["items"][0]
    assert item["updated_at"] is not None
    assert item["assigned_to"] == str(manager.id)
    assert item["assignment_status"] == "assigned"


# ---------------------------------------------------------------------------
# A2 — побочные эффекты: lead assigned, ровно одна activity/notification/audit
# ---------------------------------------------------------------------------

@skip_no_pg
@pytest.mark.asyncio
async def test_a2_side_effects_are_written_exactly_once(db, workspace):
    from app.activity.models import Activity
    from app.audit.models import AuditLog
    from app.leads.models import Lead
    from app.notifications.models import Notification

    head = await _user(db, workspace.id, "head", "Head")
    manager = await _user(db, workspace.id, "manager", "Kirill")
    lead = await _lead(db, workspace.id)

    res = await call(
        db, head, "POST", "/leads/assign",
        json={
            "to_user_id": str(manager.id),
            "mode": "ids",
            "lead_ids": [str(lead.id)],
        },
    )
    assert res.status_code == 200, (
        f"A2: запрос должен дойти до 200 раньше, чем проверять побочные "
        f"эффекты. Получили {res.status_code} {res.text}"
    )

    # Перечитываем ту же сессию новым SELECT — commit роутера уже случился.
    refreshed = (
        await db.execute(select(Lead).where(Lead.id == lead.id))
    ).scalar_one()
    assert refreshed.assignment_status == "assigned"
    assert refreshed.assigned_to == manager.id
    assert refreshed.updated_at is not None

    activities = (
        await db.execute(
            select(Activity).where(
                Activity.lead_id == lead.id, Activity.type == "lead_assigned"
            )
        )
    ).scalars().all()
    assert len(activities) == 1, (
        f"A2: ожидали ровно одну activity lead_assigned, получили {len(activities)}"
    )

    notifications = (
        await db.execute(
            select(Notification).where(
                Notification.user_id == manager.id,
                Notification.kind == "leads_assigned",
            )
        )
    ).scalars().all()
    assert len(notifications) == 1, (
        f"A2: ожидали ровно одно уведомление получателю, получили {len(notifications)}"
    )

    audit_rows = (
        await db.execute(
            select(AuditLog).where(
                AuditLog.entity_id == lead.id,
                AuditLog.action == "lead.assign_batch",
            )
        )
    ).scalars().all()
    assert len(audit_rows) == 1, (
        f"A2: ожидали ровно одну audit-запись lead.assign_batch, получили {len(audit_rows)}"
    )


# ---------------------------------------------------------------------------
# A3 — only_pool=False перехватывает занятую карточку, transferred_from заполнен
# ---------------------------------------------------------------------------

@skip_no_pg
@pytest.mark.asyncio
async def test_a3_only_pool_false_intercepts_a_card_owned_by_another_manager(db, workspace):
    head = await _user(db, workspace.id, "head", "Head")
    old_owner = await _user(db, workspace.id, "manager", "Old")
    new_owner = await _user(db, workspace.id, "manager", "New")
    lead = await _lead(db, workspace.id, assignment_status="assigned", assigned_to=old_owner.id)

    res = await call(
        db, head, "POST", "/leads/assign",
        json={
            "to_user_id": str(new_owner.id),
            "mode": "ids",
            "only_pool": False,
            "lead_ids": [str(lead.id)],
        },
    )

    assert res.status_code == 200, (
        "A3: перехват занятой карточки с only_pool=False должен вернуть "
        f"200. Фактический ответ: {res.status_code} {res.text}"
    )
    body = res.json()
    item = body["items"][0]
    assert item["transferred_from"] == str(old_owner.id), body
    assert item["assigned_to"] == str(new_owner.id)
    assert item["assignment_status"] == "assigned"
    assert item["updated_at"] is not None


# ---------------------------------------------------------------------------
# A4 — mode=filter продолжает работать (короткая регрессия)
# ---------------------------------------------------------------------------

@skip_no_pg
@pytest.mark.asyncio
async def test_a4_mode_filter_still_returns_200(db, workspace):
    head = await _user(db, workspace.id, "head", "Head")
    manager = await _user(db, workspace.id, "manager", "Kirill")
    await _lead(db, workspace.id, city="Казань")

    res = await call(
        db, head, "POST", "/leads/assign",
        json={
            "to_user_id": str(manager.id),
            "mode": "filter",
            "cities": ["Казань"],
            "limit": 10,
        },
    )

    assert res.status_code == 200, (
        f"A4: mode=filter — регрессия, ожидали 200, получили "
        f"{res.status_code} {res.text}"
    )
    body = res.json()
    assert body["assigned_count"] == 1, body