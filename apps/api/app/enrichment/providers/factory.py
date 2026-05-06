"""LLM provider factory with fallback chain."""
from __future__ import annotations

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
from app.enrichment.providers.mimo import MiMoProvider

log = structlog.get_logger()

_REGISTRY: dict[str, LLMProvider] = {
    "mimo": MiMoProvider(),
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
    """Try each provider in the chain until one succeeds. Raises LLMError if all fail."""
    s = get_settings()
    chain = chain or s.llm_fallback_chain
    last_error: LLMError | None = None
    for provider_name in chain:
        try:
            provider = get_llm_provider(provider_name)
        except KeyError:
            log.warning("llm.unknown_provider_in_chain", provider=provider_name)
            continue
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
            )
            return result
        except LLMError as e:
            log.warning(
                "llm.fallback",
                provider=provider_name,
                error_type=type(e).__name__,
                status=e.status,
                message=str(e)[:200],
            )
            last_error = e
            continue
    raise last_error or LLMError("no providers in chain", provider="factory")
