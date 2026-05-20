"""Sprint 4.0 — complete_with_fallback records usage on success."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.test_webforms import _stub_sqlalchemy  # type: ignore

_stub_sqlalchemy()


@pytest.mark.asyncio
async def test_factory_records_usage_on_success():
    from app.enrichment.providers import factory
    from app.enrichment.providers.base import CompletionResult, TaskType

    result = CompletionResult(
        text="ok", model="mimo-flash", provider="mimo",
        prompt_tokens=10, completion_tokens=5, cost_usd=0.0003,
    )
    fake_provider = MagicMock()
    fake_provider.complete = AsyncMock(return_value=result)

    db = MagicMock()
    ws = uuid.uuid4()

    with patch.object(factory, "get_llm_provider", return_value=fake_provider):
        with patch("app.llm_usage.service.record_llm_usage", new=AsyncMock()) as rec:
            out = await factory.complete_with_fallback(
                system="s", user="u", task_type=TaskType.research_synthesis,
                chain=["mimo"], db=db, workspace_id=ws,
            )

    assert out is result
    rec.assert_awaited_once()
    _, kwargs = rec.call_args
    assert kwargs["workspace_id"] == ws
    assert kwargs["task_type"] == "research_synthesis"


@pytest.mark.asyncio
async def test_factory_skips_recording_without_db():
    from app.enrichment.providers import factory
    from app.enrichment.providers.base import CompletionResult, TaskType

    result = CompletionResult(text="ok", model="m", provider="mimo")
    fake_provider = MagicMock()
    fake_provider.complete = AsyncMock(return_value=result)

    with patch.object(factory, "get_llm_provider", return_value=fake_provider):
        with patch("app.llm_usage.service.record_llm_usage", new=AsyncMock()) as rec:
            await factory.complete_with_fallback(
                system="s", user="u", task_type=TaskType.prefilter, chain=["mimo"],
            )
    rec.assert_not_awaited()
