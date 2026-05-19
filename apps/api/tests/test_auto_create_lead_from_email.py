"""Sprint 3.7 G3 — auto_create_lead_from_email task core."""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.test_webforms import _stub_sqlalchemy  # type: ignore

_stub_sqlalchemy()


@pytest.mark.asyncio
async def test_low_confidence_drops_silently():
    """confidence < 0.85 → no DB writes, no LLM follow-up."""
    from app.scheduled import jobs as j

    fake_llm = AsyncMock(return_value=MagicMock(
        text='{"action": "create_lead", "company_name": "X", '
             '"contact_name": "Y", "confidence": 0.7}',
        cost_usd=0.0,
    ))

    with patch.object(j, "_create_lead_from_email_payload", new=AsyncMock()) as mk:
        with patch.object(j, "complete_with_fallback", new=fake_llm):
            out = await j._run_auto_create_or_ignore(
                workspace_id=uuid.uuid4(),
                channel_user_id=uuid.uuid4(),
                from_email="ivan@unknown.ru",
                subject="X",
                body_preview="Y",
                gmail_message_id="g-1",
                received_at_iso="2026-05-19T10:00:00+00:00",
            )

    mk.assert_not_awaited()
    assert out["action"] == "ignore_low_confidence"


@pytest.mark.asyncio
async def test_ignore_action_drops_silently():
    """confidence ≥ 0.85 but action=='ignore' → no DB writes."""
    from app.scheduled import jobs as j

    fake_llm = AsyncMock(return_value=MagicMock(
        text='{"action": "ignore", "company_name": "", '
             '"contact_name": "", "confidence": 0.95}',
        cost_usd=0.0,
    ))

    with patch.object(j, "_create_lead_from_email_payload", new=AsyncMock()) as mk:
        with patch.object(j, "complete_with_fallback", new=fake_llm):
            out = await j._run_auto_create_or_ignore(
                workspace_id=uuid.uuid4(),
                channel_user_id=uuid.uuid4(),
                from_email="event@some-conference.ru",
                subject="Welcome",
                body_preview="...",
                gmail_message_id="g-2",
                received_at_iso="2026-05-19T10:00:00+00:00",
            )

    mk.assert_not_awaited()
    assert out["action"] == "ignore_ai"


@pytest.mark.asyncio
async def test_high_confidence_create_lead_fires_factory():
    """confidence ≥ 0.85 AND action='create_lead' → factory invoked."""
    from app.scheduled import jobs as j

    fake_llm = AsyncMock(return_value=MagicMock(
        text='{"action": "create_lead", "company_name": "Coffee Zarya", '
             '"contact_name": "Ivan Petrov", "confidence": 0.92}',
        cost_usd=0.0,
    ))

    with patch.object(j, "_create_lead_from_email_payload", new=AsyncMock(
        return_value=uuid.uuid4()
    )) as mk:
        with patch.object(j, "complete_with_fallback", new=fake_llm):
            out = await j._run_auto_create_or_ignore(
                workspace_id=uuid.uuid4(),
                channel_user_id=uuid.uuid4(),
                from_email="ivan@coffee-zarya.ru",
                subject="Запрос КП",
                body_preview="Интересует пилот DrinkX",
                gmail_message_id="g-3",
                received_at_iso="2026-05-19T10:00:00+00:00",
            )

    mk.assert_awaited_once()
    assert out["action"] == "lead_created"
    assert out["confidence"] == 0.92


@pytest.mark.asyncio
async def test_llm_failure_drops_silently():
    """Any LLMError / parse failure → no DB writes, no exception out."""
    from app.scheduled import jobs as j
    from app.enrichment.providers.base import LLMError

    fake_llm = AsyncMock(side_effect=LLMError("boom", provider="mimo"))

    with patch.object(j, "_create_lead_from_email_payload", new=AsyncMock()) as mk:
        with patch.object(j, "complete_with_fallback", new=fake_llm):
            out = await j._run_auto_create_or_ignore(
                workspace_id=uuid.uuid4(),
                channel_user_id=uuid.uuid4(),
                from_email="ivan@coffee-zarya.ru",
                subject="X",
                body_preview="Y",
                gmail_message_id="g-4",
                received_at_iso="2026-05-19T10:00:00+00:00",
            )

    mk.assert_not_awaited()
    assert out["action"] == "ignore_llm_error"
