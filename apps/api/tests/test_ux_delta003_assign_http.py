"""UX-DELTA-003: POST /leads/assign в режиме `mode=ids` отвечал 500 после commit.

Карточка в базе уже была выдана, а ответ падал на сериализации
`LeadAssignOut.items[*].updated_at`: атрибут протухал после flush
(`onupdate=func.now()` в TimestampedMixin), а ленивая догрузка в async
невозможна — `MissingGreenlet`.

Режим `filter` этим не болел (строки перечитываются), HTTP-теста на
`mode=ids` не было — дефект не ловился.
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


async def _lead(db, workspace_id, *, assigned_to=None, assignment_status="pool"):
    from app.leads import repositories as repo

    return await repo.create_lead(
        db,
        workspace_id,
        {"company_name": f"Company {uuid.uuid4().hex[:6]}"},
        assigned_to=assigned_to,
        assignment_status=assignment_status,
    )


async def call(db, actor, method: str, path: str, **kwargs):
    """Настоящий HTTP-запрос: подменяются только сессия и пользователь."""
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


@skip_no_pg
@pytest.mark.asyncio
async def test_assign_by_ids_returns_200_with_filled_items(db, workspace):
    head = await _user(db, workspace.id, "head", "Head")
    manager = await _user(db, workspace.id, "manager", "Manager")
    leads = [await _lead(db, workspace.id), await _lead(db, workspace.id)]

    res = await call(
        db,
        head,
        "POST",
        "/leads/assign",
        json={
            "to_user_id": str(manager.id),
            "mode": "ids",
            "lead_ids": [str(lead.id) for lead in leads],
        },
    )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["assigned_count"] == 2, body
    assert len(body["items"]) == 2, body
    for item in body["items"]:
        assert item["assigned_to"] == str(manager.id), item
        assert item["assignment_status"] == "assigned", item
        assert item["updated_at"] is not None, item


@skip_no_pg
@pytest.mark.asyncio
async def test_assign_by_ids_one_lead_by_admin(db, workspace):
    admin = await _user(db, workspace.id, "admin", "Admin")
    manager = await _user(db, workspace.id, "manager", "Manager")
    lead = await _lead(db, workspace.id)

    res = await call(
        db,
        admin,
        "POST",
        "/leads/assign",
        json={
            "to_user_id": str(manager.id),
            "mode": "ids",
            "lead_ids": [str(lead.id)],
        },
    )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["assigned_count"] == 1, body
    assert body["items"][0]["updated_at"] is not None, body


@skip_no_pg
@pytest.mark.asyncio
async def test_assign_by_ids_can_take_over_a_busy_lead(db, workspace):
    """`only_pool=False` — перехват занятой карточки: прежний владелец в ответе."""
    head = await _user(db, workspace.id, "head", "Head")
    old_owner = await _user(db, workspace.id, "manager", "Owner")
    manager = await _user(db, workspace.id, "manager", "Manager")
    lead = await _lead(
        db, workspace.id, assigned_to=old_owner.id, assignment_status="assigned"
    )

    res = await call(
        db,
        head,
        "POST",
        "/leads/assign",
        json={
            "to_user_id": str(manager.id),
            "mode": "ids",
            "only_pool": False,
            "lead_ids": [str(lead.id)],
        },
    )

    assert res.status_code == 200, res.text
    item = res.json()["items"][0]
    assert item["assigned_to"] == str(manager.id), item
    assert item["transferred_from"] == str(old_owner.id), item
    assert item["updated_at"] is not None, item
