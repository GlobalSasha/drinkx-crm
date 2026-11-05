"""Бренд лида: AeroMilk или DrinkX.

Отдельное поле рядом с `deal_equipment`, где лежит модель аппарата. Здесь
закреплено, что выбор сохраняется, неверное значение отклоняется, модель при
этом не меняется, а база лидов фильтрует и считает по бренду.
"""
from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

import app.main  # noqa: F401  — настраивает мапперы SQLAlchemy
from tests.conftest import POSTGRES_AVAILABLE

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires PostgreSQL")


async def _admin(db, workspace_id):
    from app.auth.models import User

    user = User(
        workspace_id=workspace_id,
        email=f"admin-{uuid.uuid4().hex[:6]}@example.com",
        name="Админ",
        role="admin",
    )
    db.add(user)
    await db.flush()
    return user


async def _lead(db, workspace_id, **fields):
    from app.leads.models import Lead

    lead = Lead(
        workspace_id=workspace_id,
        company_name=f"Компания {uuid.uuid4().hex[:6]}",
        assignment_status="pool",
        **fields,
    )
    db.add(lead)
    await db.flush()
    return lead


async def _request(db, actor, method: str, path: str, **kwargs):
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
async def test_brand_is_saved_changed_and_cleared_without_touching_equipment(db, workspace):
    actor = await _admin(db, workspace.id)
    lead = await _lead(db, workspace.id, deal_equipment="S400")
    path = f"/leads/{lead.id}/deal"

    for value in ("AeroMilk", "DrinkX", None):
        response = await _request(db, actor, "PATCH", path, json={"deal_brand": value})
        assert response.status_code == 200, response.text
        assert response.json()["deal_brand"] == value

        # То, что откроет карточка после перезагрузки.
        reread = await _request(db, actor, "GET", f"/leads/{lead.id}")
        assert reread.json()["deal_brand"] == value
        assert reread.json()["deal_equipment"] == "S400"


@skip_no_pg
@pytest.mark.asyncio
async def test_equipment_patch_leaves_brand_alone(db, workspace):
    actor = await _admin(db, workspace.id)
    lead = await _lead(db, workspace.id, deal_brand="DrinkX")

    response = await _request(
        db, actor, "PATCH", f"/leads/{lead.id}/deal", json={"deal_equipment": "S100"}
    )

    assert response.status_code == 200, response.text
    assert response.json()["deal_brand"] == "DrinkX"
    assert response.json()["deal_equipment"] == "S100"


@skip_no_pg
@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["S400", "aeromilk", "", "Lavazza"])
async def test_unknown_brand_is_rejected(db, workspace, value):
    actor = await _admin(db, workspace.id)
    lead = await _lead(db, workspace.id, deal_brand="AeroMilk")

    response = await _request(
        db, actor, "PATCH", f"/leads/{lead.id}/deal", json={"deal_brand": value}
    )

    assert response.status_code == 422
    reread = await _request(db, actor, "GET", f"/leads/{lead.id}")
    assert reread.json()["deal_brand"] == "AeroMilk"


@skip_no_pg
@pytest.mark.asyncio
async def test_pool_filters_and_counts_by_brand(db, workspace):
    actor = await _admin(db, workspace.id)
    aero = await _lead(db, workspace.id, deal_brand="AeroMilk")
    await _lead(db, workspace.id, deal_brand="DrinkX")
    await _lead(db, workspace.id, deal_brand="DrinkX")
    await _lead(db, workspace.id)

    listed = await _request(db, actor, "GET", "/leads/pool", params={"deal_brand": "AeroMilk"})
    assert listed.status_code == 200, listed.text
    assert [item["id"] for item in listed.json()["items"]] == [str(aero.id)]

    facets = await _request(db, actor, "GET", "/leads/pool/facets")
    assert facets.status_code == 200, facets.text
    counts = {row["value"]: row["count"] for row in facets.json()["deal_brands"]}
    assert counts == {"AeroMilk": 1, "DrinkX": 2}


def test_selection_survives_json_round_trip():
    """Экспорт и «Выдать по фильтру» читают выборку из JSON."""
    from app.leads.selection import LeadSelection

    selection = LeadSelection.pool(deal_brands=["DrinkX"])

    assert LeadSelection.from_json(selection.to_json()) == selection
