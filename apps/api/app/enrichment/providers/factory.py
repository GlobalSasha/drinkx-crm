"""LLM provider factory with fallback chain."""
from __future__ import annotations

import time

import structlog

from app.config import get_settings
from app.enrichment.providers.anthropic import AnthropicProvider
from app.enrichment.providers.base import (
    CompletionResult,
    LLMError,
    LLMProvider,
    TaskType,
)
from app.enrichment.providers.deepseek import DeepSeekProvider
from app.enrichment.providers.gemini import GeminiProvider
from app.enrichment.providers.groq import GroqProvider
from app.enrichment.providers.mimo import MiMoProvider

log = structlog.get_logger()

_REGISTRY: dict[str, LLMProvider] = {
    "mimo": MiMoProvider(),
    "groq": GroqProvider(),
    "anthropic": AnthropicProvider(),
    "gemini": GeminiProvider(),
    "deepseek": DeepSeekProvider(),
}


def get_llm_provider(name: str) -> LLMProvider:
    """Get a single provider by name. Raises KeyError if unknown."""
    if name not in _REGISTRY:
        raise KeyError(f"unknown provider: {name}")
    return _REGISTRY[name]


async def complete_with_fallback(
    *,
    system: str,
    user: str,
    task_type: TaskType,
    max_tokens: int = 1024,
    temperature: float = 0.4,
    timeout_seconds: float = 30.0,
    chain: list[str] | None = None,
) -> CompletionResult:
    """Try each provider in the chain until one succeeds. Raises LLMError if all fail.

    The error raised when all providers fail summarizes EVERY attempt's reason —
    not just the last one — so operators don't see misleading
    'DEEPSEEK_API_KEY not set' when MiMo silently timed out two providers earlier.
    """
    s = get_settings()
    chain = chain or s.llm_fallback_chain
    attempts: list[tuple[str, str]] = []  # (provider, short reason)
    for provider_name in chain:
        try:
            provider = get_llm_provider(provider_name)
        except KeyError:
            log.warning("llm.unknown_provider_in_chain", provider=provider_name)
            attempts.append((provider_name, "unknown provider"))
            continue
        attempt_start = time.perf_counter()
        try:
            log.info("llm.attempt", provider=provider_name, task_type=task_type.value)
            result = await provider.complete(
                system=system,
                user=user,
                task_type=task_type,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout_seconds=timeout_seconds,
            )
            log.info(
                "llm.success",
                provider=provider_name,
                model=result.model,
                tokens=result.prompt_tokens + result.completion_tokens,
                cost_usd=round(result.cost_usd, 5),
                duration_ms=int((time.perf_counter() - attempt_start) * 1000),
            )
            return result
        except LLMError as e:
            duration_ms = int((time.perf_counter() - attempt_start) * 1000)
            reason = f"{type(e).__name__}({e.status or '-'}): {str(e)[:120]}"
            log.warning(
                "llm.fallback",
                provider=provider_name,
                reason=reason,
                duration_ms=duration_ms,
            )
            attempts.append((provider_name, reason))
            continue

    # All providers failed — surface the full chain in the raised error
    summary = "; ".join(f"{name}={reason}" for name, reason in attempts) or "empty chain"
    raise LLMError(f"all providers failed: {summary}", provider="factory")
