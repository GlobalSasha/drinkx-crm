"""«Города и продукты» на /today: разбор написания и что попадает в счёт."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

import app.main  # noqa: F401  — настраивает мапперы SQLAlchemy
from app.company import services as svc
from app.company.cities_products import (
    city_from_payload,
    find_products,
    normalize_city,
    products_from_payload,
)
from tests.conftest import POSTGRES_AVAILABLE

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires PostgreSQL")


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("москва", "Москва"),
        ("  г. Москва ", "Москва"),
        ("СПб", "Санкт-Петербург"),
        ("ростов-на-дону", "Ростов-на-Дону"),
        ("нижний новгород", "Нижний Новгород"),
        ("Гродно", "Гродно"),
        ("Москва Маросейка 11/4с1", "Москва"),
        ("Москва , Покровский бульвар 11", "Москва"),
        ("Санкт-Петербург, ул. Бабушкина, д. 3", "Санкт-Петербург"),
        ("Москве по адресу: 111397, г. Москва", "Москва"),
        ("Нижний Новгород Большая Покровская 5", "Нижний Новгород"),
        ("Южно - Сахалинск", "Южно-Сахалинск"),
        ("Москвв", "Москва"),
        ("", None),
        (None, None),
    ],
)
def test_normalize_city(raw, expected):
    assert normalize_city(raw) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("S100\\S400", {"S100", "S400"}),
        ("s400 integration", {"S400"}),
        ("S100int/S400int", {"S100", "S400"}),
        ("интересует С400", {"S400"}),
        ("Аэромилк и s 300", {"AeroMilk", "S300"}),
        ("сеть с 100 точками", set()),
        ("BS400", set()),
        ("S4000", set()),
        ("хочу кофемашину", set()),
    ],
)
def test_find_products(text, expected):
    assert find_products(text) == expected


def test_payload_parsing():
    blob = {"comment": "Имя: Иван\nГород: казань\nИнтересует модель: S200\nСообщение: сравниваю с S400"}
    assert city_from_payload(blob) == "казань"
    assert products_from_payload(blob) == {"S200", "S400"}
    # Адрес страницы в «Источнике» интересом к продукту не считается.
    source_only = {"comment": "Имя: Иван\nИсточник: drinkx.ru/s400"}
    assert products_from_payload(source_only) == set()
    assert city_from_payload({"city": "Омск"}) == "Омск"
    assert products_from_payload("не словарь") == set()


async def _lead(db, workspace_id, payloads=(), **fields):
    from app.forms.models import FormSubmission, WebForm
    from app.leads.models import Lead

    fields.setdefault("assignment_status", "pool")
    lead = Lead(workspace_id=workspace_id, company_name=f"К {uuid.uuid4().hex[:6]}", **fields)
    db.add(lead)
    await db.flush()
    if payloads:
        form = WebForm(workspace_id=workspace_id, name="Сайт",
                       slug=f"s-{uuid.uuid4().hex[:6]}", fields_json=[])
        db.add(form)
        await db.flush()
        for payload in payloads:
            db.add(FormSubmission(web_form_id=form.id, lead_id=lead.id, raw_payload=payload))
        await db.flush()
    return lead


@skip_no_pg
async def test_counts_the_whole_live_base(db, workspace):
    now = datetime.now(timezone.utc)
    await _lead(db, workspace.id, city="москва", deal_equipment="S100 S400")
    # Поле карточки важнее заявки; повторное упоминание продукта — один лид.
    await _lead(db, workspace.id, city="Москва",
                payloads=[{"comment": "Имя: А\nГород: Казань\nИнтересует модель: S400"},
                          {"comment": "Имя: А\nСообщение: всё ещё S400"}])
    await _lead(db, workspace.id, payloads=[{"comment": "Имя: Б\nГород: казань"}], deal_brand="AeroMilk")
    await _lead(db, workspace.id, won_at=now, deal_equipment="S200")  # закрытые — тоже база
    await _lead(db, workspace.id, city="Удалённый", deal_equipment="S300", deleted_at=now)
    await _lead(db, workspace.id, city="Архивный", deal_equipment="S300", archived_at=now)

    out = await svc.cities_products(db, workspace_id=workspace.id)

    assert out["total"] == 4
    assert out["cities"] == [{"name": "Москва", "count": 2}, {"name": "Казань", "count": 1}]
    assert out["no_city"] == 1
    assert {p["name"]: p["count"] for p in out["products"]} == {
        "S100": 1, "S200": 1, "S300": 0, "S400": 2, "AeroMilk": 1,
    }
    assert out["no_product"] == 0


@skip_no_pg
async def test_manager_is_refused(db, workspace, user):
    from app.auth.dependencies import current_user
    from app.db import get_db
    from app.main import app as fastapi_app

    fastapi_app.dependency_overrides[get_db] = lambda: db
    fastapi_app.dependency_overrides[current_user] = lambda: user
    try:
        transport = ASGITransport(app=fastapi_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/company/cities-products")
    finally:
        fastapi_app.dependency_overrides.clear()
    assert response.status_code == 403
