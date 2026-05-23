import json
from types import SimpleNamespace

import pytest

from app.base_update import extractor
from app.base_update.schemas import ExtractedCard


@pytest.mark.asyncio
async def test_extract_card_parses_llm_json(monkeypatch):
    payload = {
        "company": {"name": "ООО Ромашка", "city": "Москва", "priority": "A"},
        "contacts": [{"name": "Иван Петров", "title": "Директор", "role_type": "economic_buyer"}],
        "ai_brief": "Сеть кофеен, 12 точек.",
        "extraction_confidence": 0.82,
    }

    async def fake_complete(**kwargs):
        return SimpleNamespace(text=json.dumps(payload), cost_usd=0.0)

    monkeypatch.setattr(extractor, "complete_with_fallback", fake_complete)
    card = await extractor.extract_card("# Ромашка\n...", db=None, workspace_id=None)
    assert isinstance(card, ExtractedCard)
    assert card.company.name == "ООО Ромашка"
    assert card.contacts[0].role_type == "economic_buyer"
    assert card.extraction_confidence == 0.82


@pytest.mark.asyncio
async def test_extract_card_survives_non_json(monkeypatch):
    async def fake_complete(**kwargs):
        return SimpleNamespace(text="sorry I cannot", cost_usd=0.0)

    monkeypatch.setattr(extractor, "complete_with_fallback", fake_complete)
    card = await extractor.extract_card("garbage", db=None, workspace_id=None)
    assert card.company.name == ""        # falls back to empty, never raises
    assert card.extraction_confidence == 0.0


@pytest.mark.asyncio
async def test_extract_card_strips_code_fence(monkeypatch):
    payload = {"company": {"name": "X"}, "extraction_confidence": 0.7}
    fenced = "```json\n" + json.dumps(payload) + "\n```"

    async def fake_complete(**kwargs):
        return SimpleNamespace(text=fenced, cost_usd=0.0)

    monkeypatch.setattr(extractor, "complete_with_fallback", fake_complete)
    card = await extractor.extract_card("doc", db=None, workspace_id=None)
    assert card.company.name == "X"
    assert card.extraction_confidence == 0.7
