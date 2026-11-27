"""Страна и адрес лида — отдельные поля рядом с городом.

Раньше в «Город» писали адрес целиком, и в фильтрах каждый адрес становился
отдельным «городом». Здесь закреплено, что страна и адрес сохраняются из
карточки, база лидов фильтрует и считает по стране, выборка переживает JSON
(экспорт и «Выдать по фильтру»), а загрузка из файла и форма с сайта кладут
страну и адрес в свои поля.
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
async def test_country_and_address_are_saved_from_the_card(db, workspace):
    actor = await _admin(db, workspace.id)
    lead = await _lead(db, workspace.id, city="Москва")

    response = await _request(
        db, actor, "PATCH", f"/leads/{lead.id}",
        json={"country": "Россия", "address": "ул. Маросейка, 11/4с1"},
    )
    assert response.status_code == 200, response.text

    reread = await _request(db, actor, "GET", f"/leads/{lead.id}")
    body = reread.json()
    assert body["country"] == "Россия"
    assert body["address"] == "ул. Маросейка, 11/4с1"
    assert body["city"] == "Москва"


@skip_no_pg
@pytest.mark.asyncio
async def test_too_long_country_is_rejected(db, workspace):
    actor = await _admin(db, workspace.id)
    lead = await _lead(db, workspace.id)

    response = await _request(
        db, actor, "PATCH", f"/leads/{lead.id}", json={"country": "Р" * 81}
    )

    assert response.status_code == 422


@skip_no_pg
@pytest.mark.asyncio
async def test_pool_filters_and_counts_by_country(db, workspace):
    actor = await _admin(db, workspace.id)
    minsk = await _lead(db, workspace.id, city="Минск", country="Беларусь")
    await _lead(db, workspace.id, city="Москва", country="Россия")
    await _lead(db, workspace.id, city="Казань", country="Россия")
    await _lead(db, workspace.id)

    listed = await _request(db, actor, "GET", "/leads/pool", params={"country": "Беларусь"})
    assert listed.status_code == 200, listed.text
    assert [item["id"] for item in listed.json()["items"]] == [str(minsk.id)]

    facets = await _request(db, actor, "GET", "/leads/pool/facets")
    assert facets.status_code == 200, facets.text
    counts = {row["value"]: row["count"] for row in facets.json()["countries"]}
    assert counts == {"Беларусь": 1, "Россия": 2}


def test_selection_with_countries_survives_json_round_trip():
    """Экспорт и «Выдать по фильтру» читают выборку из JSON."""
    from app.leads.selection import LeadSelection

    selection = LeadSelection.pool(countries=["Россия", "Беларусь"])

    assert LeadSelection.from_json(selection.to_json()) == selection
    assert selection.to_json()["countries"] == ["Россия", "Беларусь"]


def test_assign_filter_body_carries_countries():
    from app.leads.schemas import LeadAssignIn

    body = LeadAssignIn(mode="filter", to_user_id=uuid.uuid4(), countries=["Казахстан"])

    assert body.to_selection().countries == ("Казахстан",)


def test_import_maps_country_and_address_columns_to_their_own_fields():
    from app.import_export.field_map import DIRECT_LEAD_COLUMNS, LEAD_IMPORT_FIELDS

    assert "страна" in LEAD_IMPORT_FIELDS["country"].aliases
    assert "адрес" in LEAD_IMPORT_FIELDS["address"].aliases
    assert {"country", "address"} <= DIRECT_LEAD_COLUMNS
    # Адрес не должен уезжать в город, как раньше.
    assert "адрес" not in LEAD_IMPORT_FIELDS["city"].aliases
