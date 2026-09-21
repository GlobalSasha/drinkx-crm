"""ARCH-03 DRIFT-1: бейдж «AI создал · N%» на /leads-pool всегда показывал 0%.

`NeedsReviewRow` читал `ai_data.auto_create_confidence`, а список отдаёт
`LeadListItemOut`, в которой `ai_data` намеренно нет (он бывает и 50 КБ на
лид). Ключа не было в JSON вообще, `?? 0` превращал это в «0%» на каждой
карточке, и руководитель принимал «Подтвердить / Не лид», глядя на цифру,
которая всегда врала в меньшую сторону.

Исправление минимальное: одно скалярное поле `ai_confidence` в схеме списка,
считается в SQL, `ai_data` остаётся deferred. Здесь закреплено, что поле
есть, совпадает с `ai_data` и не тянет за собой сам payload.
"""
from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

import app.main  # noqa: F401  — настраивает мапперы SQLAlchemy
from tests.conftest import POSTGRES_AVAILABLE

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires PostgreSQL")

CONFIDENCE = 0.85


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


async def _pool_lead(db, workspace_id, *, company_name: str, ai_data: dict | None):
    from app.leads.models import Lead

    lead = Lead(
        workspace_id=workspace_id,
        company_name=company_name,
        assignment_status="pool",
        needs_review=ai_data is not None,
        ai_data=ai_data,
    )
    db.add(lead)
    await db.flush()
    return lead


async def _get(db, actor, path: str):
    from app.auth.dependencies import current_user
    from app.db import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[current_user] = lambda: actor
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get(path)
    finally:
        app.dependency_overrides.clear()


@skip_no_pg
@pytest.mark.asyncio
async def test_pool_row_carries_the_ai_confidence_from_ai_data(db, workspace):
    head = await _user(db, workspace.id, "head", "Руководитель")
    ai_lead = await _pool_lead(
        db, workspace.id,
        company_name=f"AI-лид {uuid.uuid4().hex[:6]}",
        ai_data={"auto_create_confidence": CONFIDENCE, "brief": "x" * 1000},
    )
    manual_lead = await _pool_lead(
        db, workspace.id,
        company_name=f"Ручной лид {uuid.uuid4().hex[:6]}",
        ai_data=None,
    )

    res = await _get(db, head, "/leads/pool?page_size=50")
    assert res.status_code == 200, res.text
    by_id = {item["id"]: item for item in res.json()["items"]}

    ai_row = by_id[str(ai_lead.id)]
    assert ai_row["ai_confidence"] == pytest.approx(CONFIDENCE)
    # Само по себе число, а не весь payload: список остаётся слим-ответом.
    assert "ai_data" not in ai_row

    # Лид без AI-данных — None, а не 0.0: «не создавал AI» и «AI не уверен»
    # это разные вещи, и бейдж на такой карточке не рисуется вовсе.
    assert by_id[str(manual_lead.id)]["ai_confidence"] is None


@skip_no_pg
@pytest.mark.asyncio
async def test_single_lead_read_still_returns_the_whole_ai_data(db, workspace):
    """Карточка лида не затронута: `GET /leads/{id}` как отдавал `ai_data`
    целиком, так и отдаёт."""
    head = await _user(db, workspace.id, "head", "Руководитель")
    lead = await _pool_lead(
        db, workspace.id,
        company_name=f"AI-лид {uuid.uuid4().hex[:6]}",
        ai_data={"auto_create_confidence": CONFIDENCE},
    )

    res = await _get(db, head, f"/leads/{lead.id}")
    assert res.status_code == 200, res.text
    assert res.json()["ai_data"]["auto_create_confidence"] == pytest.approx(CONFIDENCE)
