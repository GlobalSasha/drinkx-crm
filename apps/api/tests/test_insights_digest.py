"""«Сводка за 5 дней»: what the worker gets, which lines the CRM keeps, the card."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import POSTGRES_AVAILABLE
from tests.test_insights import _comment, _lead

from app.insights import digest as dg
from app.insights.schemas import DigestIn

skip_no_pg = pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="requires Postgres")


@skip_no_pg
async def test_source_groups_recent_manager_comments_by_lead(db, workspace, user):
    lead = await _lead(db, workspace, user, name="Гуру кофе")
    await _comment(db, lead, user, "Договорились на рассрочку, звонить +7 903 217-94-16", days_ago=1)
    await _comment(db, lead, user, "жду реквизиты", days_ago=0)
    await _comment(db, lead, user, "старое", days_ago=6)  # вне 5 дней
    await _comment(db, lead, user, "заявка с сайта", by_user=False)  # не менеджер

    out = await dg.digest_source(db, workspace_id=workspace.id)

    assert [s["key"] for s in out["sections"]] == list(dg.SECTIONS)
    [src] = out["leads"]
    assert src["company_name"] == "Гуру кофе"
    texts = [c["text"] for c in src["comments"]]
    assert texts[1] == "жду реквизиты"
    assert "903" not in texts[0]
    assert len(texts) == 2


@skip_no_pg
async def test_only_checked_lines_are_kept(db, workspace, user):
    lead = await _lead(db, workspace, user, name="Винегрет")
    quiet = await _lead(db, workspace, user, name="Тишина")  # без комментариев
    await _comment(db, lead, user, "в марте берут 4 AeroMilk", days_ago=1)
    now = datetime.now(timezone.utc)

    res = await dg.store_digest(db, workspace_id=workspace.id, payload=DigestIn(
        period_from=now - timedelta(days=5), period_to=now,
        sections=[
            {"key": "progress", "items": [
                {"text": "  Винегрет: в марте  берут 4 AeroMilk ", "lead_ids": [lead.id, lead.id]},
                {"text": "Тишина: всё отлично", "lead_ids": [quiet.id]},  # нет комментариев
                {"text": "Кто-то купил", "lead_ids": [uuid.uuid4()]},  # чужой лид
                {"text": "   ", "lead_ids": [lead.id]},  # пусто
            ]},
            {"key": "advice", "items": [{"text": "Совет", "lead_ids": [lead.id]}]},  # нет раздела
        ],
    ))

    assert res == {"accepted": 1, "dropped": 4}
    card = await dg.company_digest(db, workspace_id=workspace.id)
    d = card["digest"]
    assert d["comments"] == 1 and d["leads"] == 1
    assert d["sections"] == [{"key": "progress", "title": "Продвинулись", "items": [
        {"text": "Винегрет: в марте берут 4 AeroMilk",
         "leads": [{"id": lead.id, "company_name": "Винегрет"}]},
    ]}]
    assert card["stale"] is False


@skip_no_pg
async def test_card_without_digest_is_stale_and_lists_new_leads(db, workspace, user):
    fresh = await _lead(db, workspace, user, name="Ефим Киров")
    await _lead(db, workspace, user, name="Удалённый", deleted=True)

    card = await dg.company_digest(db, workspace_id=workspace.id)

    assert card["digest"] is None
    assert card["stale"] is True
    names = [n["company_name"] for n in card["new_leads"]]
    assert names == ["Ефим Киров"]
    assert card["new_leads"][0]["id"] == fresh.id


@skip_no_pg
async def test_manager_is_refused(db, workspace, user):
    from httpx import ASGITransport, AsyncClient

    from app.auth.dependencies import current_user
    from app.db import get_db
    from app.main import app as fastapi_app

    fastapi_app.dependency_overrides[get_db] = lambda: db
    fastapi_app.dependency_overrides[current_user] = lambda: user
    try:
        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as c:
            response = await c.get("/company/digest")
    finally:
        fastapi_app.dependency_overrides.clear()
    assert response.status_code == 403
