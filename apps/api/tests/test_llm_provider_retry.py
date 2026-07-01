"""Plan 012 — bounded retry with backoff on transient LLM errors before fallback.

Verifies that `complete_with_fallback` retries the *same* provider once on a
transient error (429/5xx/unknown-status) before advancing the chain, and falls
through immediately (no retry) on a terminal error (e.g. 401).
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.enrichment.providers.base import (
    CompletionResult,
    LLMAuthError,
    LLMRateLimited,
    LLMServerError,
    TaskType,
)
from app.enrichment.providers.factory import complete_with_fallback


@pytest.mark.asyncio
async def test_transient_error_retries_same_provider_then_succeeds(monkeypatch):
    """429 on first call, success on retry — same provider used twice, no fallback."""
    import app.enrichment.providers.factory as factory_mod

    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(factory_mod.asyncio, "sleep", fake_sleep)

    call_order: list[str] = []

    async def flaky_complete(**kwargs) -> CompletionResult:
        call_order.append("mimo")
        if len(call_order) == 1:
            raise LLMRateLimited("rate limited", provider="mimo", status=429)
        return CompletionResult(text="ok", model="m", provider="mimo")

    provider = MagicMock()
    provider.name = "mimo"
    provider.complete = flaky_complete

    monkeypatch.setattr(factory_mod, "_REGISTRY", {"mimo": provider, "anthropic": MagicMock()})

    result = await complete_with_fallback(
        system="s", user="u", task_type=TaskType.prefilter, chain=["mimo", "anthropic"]
    )

    assert result.provider == "mimo"
    assert call_order == ["mimo", "mimo"]  # retried the SAME provider, no fall-through
    assert len(sleeps) == 1  # exactly one backoff sleep


@pytest.mark.asyncio
async def test_terminal_error_falls_through_immediately_no_retry(monkeypatch):
    """401 (auth) is terminal — advances to the next provider without retrying."""
    import app.enrichment.providers.factory as factory_mod

    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(factory_mod.asyncio, "sleep", fake_sleep)

    call_order: list[str] = []

    async def auth_fail(**kwargs) -> CompletionResult:
        call_order.append("mimo")
        raise LLMAuthError("unauthorized", provider="mimo", status=401)

    async def second_ok(**kwargs) -> CompletionResult:
        call_order.append("anthropic")
        return CompletionResult(text="ok", model="m", provider="anthropic")

    mimo = MagicMock()
    mimo.name = "mimo"
    mimo.complete = auth_fail

    anthropic = MagicMock()
    anthropic.name = "anthropic"
    anthropic.complete = second_ok

    monkeypatch.setattr(factory_mod, "_REGISTRY", {"mimo": mimo, "anthropic": anthropic})

    result = await complete_with_fallback(
        system="s", user="u", task_type=TaskType.prefilter, chain=["mimo", "anthropic"]
    )

    assert result.provider == "anthropic"
    assert call_order == ["mimo", "anthropic"]  # exactly one attempt on mimo, no retry
    assert sleeps == []  # no backoff sleep for a terminal error


@pytest.mark.asyncio
async def test_transient_error_exhausts_retries_then_falls_through(monkeypatch):
    """5xx on every attempt — after _MAX_RETRIES exhausted, advances to next provider."""
    import app.enrichment.providers.factory as factory_mod

    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(factory_mod.asyncio, "sleep", fake_sleep)

    call_order: list[str] = []

    async def always_500(**kwargs) -> CompletionResult:
        call_order.append("mimo")
        raise LLMServerError("down", provider="mimo", status=503)

    async def second_ok(**kwargs) -> CompletionResult:
        call_order.append("anthropic")
        return CompletionResult(text="ok", model="m", provider="anthropic")

    mimo = MagicMock()
    mimo.name = "mimo"
    mimo.complete = always_500

    anthropic = MagicMock()
    anthropic.name = "anthropic"
    anthropic.complete = second_ok

    monkeypatch.setattr(factory_mod, "_REGISTRY", {"mimo": mimo, "anthropic": anthropic})

    result = await complete_with_fallback(
        system="s", user="u", task_type=TaskType.prefilter, chain=["mimo", "anthropic"]
    )

    assert result.provider == "anthropic"
    # _MAX_RETRIES = 1 → 2 total attempts on mimo (original + 1 retry), then fallback.
    assert call_order == ["mimo", "mimo", "anthropic"]
    assert len(sleeps) == 1
