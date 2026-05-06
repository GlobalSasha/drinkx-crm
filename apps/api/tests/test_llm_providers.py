"""Tests for Sprint 1.3.A — LLM provider abstraction.

All network calls are intercepted by replacing the provider's httpx module
reference with a fake that returns predetermined responses. No real HTTP.
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.enrichment.providers.base import (
    CompletionResult,
    LLMAuthError,
    LLMError,
    LLMRateLimited,
    LLMServerError,
    TaskType,
    is_flash_task,
)
from app.enrichment.providers.factory import complete_with_fallback
from app.enrichment.schemas import DecisionMakerHint, ResearchOutput


# ---------------------------------------------------------------------------
# Mock HTTP infrastructure
# ---------------------------------------------------------------------------

class _FakeResponse:
    """Minimal httpx.Response-like object for tests."""

    def __init__(self, status_code: int, body: dict | str) -> None:
        self.status_code = status_code
        self._body = json.dumps(body) if isinstance(body, dict) else body
        self.text = self._body
        self.is_success = 200 <= status_code < 300

    def json(self) -> Any:
        return json.loads(self._body)


class _FakeAsyncClient:
    """Replaces httpx.AsyncClient for tests. Captures requests, returns fake responses."""

    def __init__(
        self,
        responses: list[tuple[int, dict | str]],
        captured: list[dict] | None = None,
    ) -> None:
        self._responses = list(responses)
        self._index = 0
        self.captured = captured if captured is not None else []

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        pass

    async def post(self, url: str, *, json: dict | None = None, headers: dict | None = None, params: dict | None = None) -> _FakeResponse:
        self.captured.append({"url": url, "json": json, "headers": headers or {}, "params": params or {}})
        status, body = self._responses[self._index]
        self._index = min(self._index + 1, len(self._responses) - 1)
        return _FakeResponse(status, body)


def _fake_httpx(responses: list[tuple[int, dict | str]], captured: list[dict]):
    """Return a fake httpx module stub with AsyncClient producing given responses."""
    client = _FakeAsyncClient(responses, captured)

    class _FakeHttpx:
        class TimeoutException(Exception):
            pass
        class HTTPError(Exception):
            pass

        @staticmethod
        def AsyncClient(**kwargs: Any) -> _FakeAsyncClient:
            return client

    return _FakeHttpx()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_settings():
    """Minimal settings for tests.

    Pass values via constructor so they take priority over any env vars
    (pydantic-settings: init args > env vars > field defaults).
    """
    from app.config import Settings

    return Settings(
        _env_file=None,
        mimo_api_key="test-mimo-key",
        mimo_base_url="https://api.xiaomimimo.com/v1",
        mimo_model_pro="mimo-v2-pro",
        mimo_model_flash="mimo-v2-flash",
        anthropic_api_key="test-anthropic-key",
        anthropic_model="claude-sonnet-4-5",
        gemini_api_key="test-gemini-key",
        gemini_model="gemini-2.0-flash-exp",
        deepseek_api_key="test-deepseek-key",
        deepseek_model="deepseek-chat",
        llm_fallback_chain=["mimo", "anthropic", "gemini", "deepseek"],
    )


def _mimo_ok_body(model: str = "mimo-v2-flash", text: str = "hello") -> dict:
    return {
        "choices": [{"message": {"content": text}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        "model": model,
    }


def _anthropic_ok_body(text: str = "hello anthropic") -> dict:
    return {
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": 8, "output_tokens": 4},
        "model": "claude-sonnet-4-5",
    }


def _gemini_ok_body(text: str = "hello gemini") -> dict:
    return {
        "candidates": [{"content": {"parts": [{"text": text}]}}],
        "usageMetadata": {"promptTokenCount": 6, "candidatesTokenCount": 3},
    }


def _deepseek_ok_body(text: str = "hello deepseek") -> dict:
    return {
        "choices": [{"message": {"content": text}}],
        "usage": {"prompt_tokens": 7, "completion_tokens": 4},
        "model": "deepseek-chat",
    }


# ---------------------------------------------------------------------------
# MiMo provider tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mimo_calls_chat_completions_with_api_key_header(monkeypatch):
    """Flash task → mimo-v2-flash; Pro task → mimo-v2-pro; api-key header present."""
    import app.enrichment.providers.mimo as mimo_mod

    captured: list[dict] = []
    fake = _fake_httpx(
        [(200, _mimo_ok_body("mimo-v2-flash")), (200, _mimo_ok_body("mimo-v2-pro"))],
        captured,
    )

    monkeypatch.setattr(mimo_mod, "get_settings", lambda: _fake_settings())
    monkeypatch.setattr(mimo_mod, "httpx", fake)

    provider = mimo_mod.MiMoProvider()

    result_flash = await provider.complete(
        system="sys", user="usr", task_type=TaskType.research_synthesis
    )
    result_pro = await provider.complete(
        system="sys", user="usr", task_type=TaskType.sales_coach
    )

    assert len(captured) == 2

    # Check URL ends with /chat/completions
    for req in captured:
        assert req["url"].endswith("/chat/completions")

    # Check api-key header present; no Bearer/authorization
    for req in captured:
        assert req["headers"].get("api-key") == "test-mimo-key"
        assert "authorization" not in req["headers"]

    # Check model selection
    assert captured[0]["json"]["model"] == "mimo-v2-flash"
    assert captured[1]["json"]["model"] == "mimo-v2-pro"

    assert result_flash.provider == "mimo"
    assert result_pro.provider == "mimo"


@pytest.mark.asyncio
async def test_mimo_429_raises_rate_limited(monkeypatch):
    import app.enrichment.providers.mimo as mimo_mod

    captured: list[dict] = []
    fake = _fake_httpx([(429, "rate limited")], captured)
    monkeypatch.setattr(mimo_mod, "get_settings", lambda: _fake_settings())
    monkeypatch.setattr(mimo_mod, "httpx", fake)

    with pytest.raises(LLMRateLimited) as exc_info:
        await mimo_mod.MiMoProvider().complete(system="s", user="u", task_type=TaskType.prefilter)
    assert exc_info.value.status == 429
    assert exc_info.value.provider == "mimo"


@pytest.mark.asyncio
async def test_mimo_401_raises_auth_error(monkeypatch):
    import app.enrichment.providers.mimo as mimo_mod

    captured: list[dict] = []
    fake = _fake_httpx([(401, "unauthorized")], captured)
    monkeypatch.setattr(mimo_mod, "get_settings", lambda: _fake_settings())
    monkeypatch.setattr(mimo_mod, "httpx", fake)

    with pytest.raises(LLMAuthError) as exc_info:
        await mimo_mod.MiMoProvider().complete(system="s", user="u", task_type=TaskType.prefilter)
    assert exc_info.value.status == 401
    assert exc_info.value.provider == "mimo"


@pytest.mark.asyncio
async def test_mimo_500_raises_server_error(monkeypatch):
    import app.enrichment.providers.mimo as mimo_mod

    captured: list[dict] = []
    fake = _fake_httpx([(500, "internal error")], captured)
    monkeypatch.setattr(mimo_mod, "get_settings", lambda: _fake_settings())
    monkeypatch.setattr(mimo_mod, "httpx", fake)

    with pytest.raises(LLMServerError) as exc_info:
        await mimo_mod.MiMoProvider().complete(system="s", user="u", task_type=TaskType.scoring)
    assert exc_info.value.status == 500
    assert exc_info.value.provider == "mimo"


# ---------------------------------------------------------------------------
# Anthropic provider tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_anthropic_uses_x_api_key_and_anthropic_version_headers(monkeypatch):
    import app.enrichment.providers.anthropic as anthropic_mod

    captured: list[dict] = []
    fake = _fake_httpx([(200, _anthropic_ok_body())], captured)
    monkeypatch.setattr(anthropic_mod, "get_settings", lambda: _fake_settings())
    monkeypatch.setattr(anthropic_mod, "httpx", fake)

    result = await anthropic_mod.AnthropicProvider().complete(
        system="sys", user="usr", task_type=TaskType.research_synthesis
    )

    assert len(captured) == 1
    req = captured[0]
    assert req["headers"].get("x-api-key") == "test-anthropic-key"
    assert req["headers"].get("anthropic-version") == "2023-06-01"
    assert result.provider == "anthropic"
    assert result.text == "hello anthropic"


@pytest.mark.asyncio
async def test_anthropic_extracts_text_from_content_blocks(monkeypatch):
    import app.enrichment.providers.anthropic as anthropic_mod

    body = {
        "content": [
            {"type": "text", "text": "part one "},
            {"type": "text", "text": "part two"},
            {"type": "tool_use", "id": "x"},  # non-text block, should be ignored
        ],
        "usage": {"input_tokens": 5, "output_tokens": 3},
        "model": "claude-sonnet-4-5",
    }
    captured: list[dict] = []
    fake = _fake_httpx([(200, body)], captured)
    monkeypatch.setattr(anthropic_mod, "get_settings", lambda: _fake_settings())
    monkeypatch.setattr(anthropic_mod, "httpx", fake)

    result = await anthropic_mod.AnthropicProvider().complete(
        system="s", user="u", task_type=TaskType.daily_plan
    )
    assert result.text == "part one part two"
    assert result.prompt_tokens == 5
    assert result.completion_tokens == 3


# ---------------------------------------------------------------------------
# Gemini provider tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_gemini_calls_v1beta_with_key_query_param(monkeypatch):
    import app.enrichment.providers.gemini as gemini_mod

    captured: list[dict] = []
    fake = _fake_httpx([(200, _gemini_ok_body())], captured)
    monkeypatch.setattr(gemini_mod, "get_settings", lambda: _fake_settings())
    monkeypatch.setattr(gemini_mod, "httpx", fake)

    result = await gemini_mod.GeminiProvider().complete(
        system="sys", user="usr", task_type=TaskType.research_synthesis
    )

    assert len(captured) == 1
    req = captured[0]
    assert "/v1beta/models/" in req["url"]
    assert req["params"].get("key") == "test-gemini-key"
    assert result.provider == "gemini"
    assert result.text == "hello gemini"


# ---------------------------------------------------------------------------
# DeepSeek provider tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_deepseek_uses_bearer_token(monkeypatch):
    import app.enrichment.providers.deepseek as deepseek_mod

    captured: list[dict] = []
    fake = _fake_httpx([(200, _deepseek_ok_body())], captured)
    monkeypatch.setattr(deepseek_mod, "get_settings", lambda: _fake_settings())
    monkeypatch.setattr(deepseek_mod, "httpx", fake)

    result = await deepseek_mod.DeepSeekProvider().complete(
        system="sys", user="usr", task_type=TaskType.scoring
    )

    assert len(captured) == 1
    req = captured[0]
    assert req["headers"].get("Authorization") == "Bearer test-deepseek-key"
    assert result.provider == "deepseek"
    assert result.text == "hello deepseek"


# ---------------------------------------------------------------------------
# Factory / fallback tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_factory_advances_chain_on_failure(monkeypatch):
    """First provider raises LLMServerError; factory tries next and returns success."""
    monkeypatch.setattr("app.config.get_settings", lambda: _fake_settings())

    call_order: list[str] = []

    async def failing_complete(**kwargs) -> CompletionResult:
        call_order.append("first")
        raise LLMServerError("boom", provider="first")

    async def succeeding_complete(**kwargs) -> CompletionResult:
        call_order.append("second")
        return CompletionResult(text="ok", model="test-model", provider="second")

    first = MagicMock()
    first.name = "first"
    first.complete = failing_complete

    second = MagicMock()
    second.name = "second"
    second.complete = succeeding_complete

    import app.enrichment.providers.factory as factory_mod
    monkeypatch.setattr(factory_mod, "_REGISTRY", {"first": first, "second": second})
    monkeypatch.setattr(factory_mod, "get_settings", lambda: _fake_settings())

    result = await complete_with_fallback(
        system="s", user="u", task_type=TaskType.prefilter, chain=["first", "second"]
    )
    assert result.text == "ok"
    assert call_order == ["first", "second"]


@pytest.mark.asyncio
async def test_factory_raises_when_all_fail(monkeypatch):
    async def failing(**kwargs):
        raise LLMServerError("down", provider="p")

    provider = MagicMock()
    provider.name = "p"
    provider.complete = failing

    import app.enrichment.providers.factory as factory_mod
    monkeypatch.setattr(factory_mod, "_REGISTRY", {"p": provider})
    monkeypatch.setattr(factory_mod, "get_settings", lambda: _fake_settings())

    with pytest.raises(LLMServerError):
        await complete_with_fallback(
            system="s", user="u", task_type=TaskType.prefilter, chain=["p"]
        )


@pytest.mark.asyncio
async def test_factory_logs_provider_attempts(monkeypatch):
    """Factory tries fallback chain; succeeds on second provider."""
    call_order: list[str] = []

    async def first_fail(**kwargs):
        call_order.append("mimo")
        raise LLMRateLimited("429", provider="mimo", status=429)

    async def second_ok(**kwargs) -> CompletionResult:
        call_order.append("anthropic")
        return CompletionResult(text="ok", model="m", provider="anthropic")

    p1 = MagicMock()
    p1.name = "mimo"
    p1.complete = first_fail

    p2 = MagicMock()
    p2.name = "anthropic"
    p2.complete = second_ok

    import app.enrichment.providers.factory as factory_mod
    monkeypatch.setattr(factory_mod, "_REGISTRY", {"mimo": p1, "anthropic": p2})
    monkeypatch.setattr(factory_mod, "get_settings", lambda: _fake_settings())

    result = await complete_with_fallback(
        system="s", user="u", task_type=TaskType.daily_plan, chain=["mimo", "anthropic"]
    )
    assert result.provider == "anthropic"
    assert call_order == ["mimo", "anthropic"]


# ---------------------------------------------------------------------------
# ResearchOutput schema tests
# ---------------------------------------------------------------------------

def test_research_output_default_values_dont_raise():
    out = ResearchOutput()
    assert out.company_profile == ""
    assert out.fit_score == 0.0
    assert out.growth_signals == []
    assert out.risk_signals == []
    assert out.decision_maker_hints == []
    assert out.next_steps == []
    assert out.sources_used == []
    assert out.urgency == ""


def test_research_output_handles_partial_dict():
    out = ResearchOutput(**{"company_profile": "X company"})
    assert out.company_profile == "X company"
    assert out.geography == ""
    assert out.fit_score == 0.0
    assert out.notes == ""


def test_research_output_decision_maker_hint_defaults():
    hint = DecisionMakerHint()
    assert hint.name == ""
    assert hint.role == ""
    assert hint.confidence == "low"


# ---------------------------------------------------------------------------
# TaskType / Flash-Pro split tests
# ---------------------------------------------------------------------------

def test_is_flash_task_mapping():
    """Flash tasks per ADR-018: research_synthesis, daily_plan, prefilter."""
    assert is_flash_task(TaskType.research_synthesis) is True
    assert is_flash_task(TaskType.daily_plan) is True
    assert is_flash_task(TaskType.prefilter) is True

    assert is_flash_task(TaskType.sales_coach) is False
    assert is_flash_task(TaskType.scoring) is False
    assert is_flash_task(TaskType.reenrichment_high_fit) is False
