"""LLM extraction of a single .md ЛПР card → ExtractedCard."""
from __future__ import annotations

import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.base_update.schemas import ExtractedCard
from app.enrichment.providers.base import TaskType
from app.enrichment.providers.factory import complete_with_fallback

_SYSTEM = (
    "Ты извлекаешь структуру из русской markdown-карточки ЛПР для B2B-CRM. "
    "Верни СТРОГО JSON по схеме {company, contacts[], ai_brief, extraction_confidence}. "
    "company: name (обяз.), segment, priority (A/B/C/D), website, inn, city, phone, email. "
    "contacts[]: name, title, role_type, email, phone, telegram, linkedin, source, confidence. "
    "role_type МАППИТСЯ в один из: economic_buyer (держит бюджет/решение), "
    "champion (продвигает внутри), technical_buyer (технические требования), "
    "operational_buyer (эксплуатация/закупка операционная). "
    "ai_brief: 2-4 предложения — описание, масштаб, кофейный сервис, триггеры, маршрут. "
    "Чего нет — null, НИЧЕГО НЕ ВЫДУМЫВАЙ. extraction_confidence: 0..1."
)


def _strip_code_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1] if "\n" in t else t[3:]
        if t.endswith("```"):
            t = t[:-3]
    return t.strip()


async def extract_card(
    md_text: str, *, db: AsyncSession | None, workspace_id: uuid.UUID | None
) -> ExtractedCard:
    completion = await complete_with_fallback(
        system=_SYSTEM,
        user=md_text[:12000],
        task_type=TaskType.lpr_extraction,
        max_tokens=1500,
        temperature=0.2,
        db=db,
        workspace_id=workspace_id,
    )
    try:
        data = json.loads(_strip_code_fence(completion.text))
        if not isinstance(data, dict):
            data = {}
    except (json.JSONDecodeError, ValueError):
        data = {}
    return ExtractedCard.model_validate(data)
