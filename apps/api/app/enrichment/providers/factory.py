"""LLM provider factory with fallback chain."""
from __future__ import annotations

import asyncio
import time
import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

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

# A transient-blip smoother, not a resilience layer: one extra attempt on the
# same provider before falling through to the next one in the chain.
_MAX_RETRIES = 1
_BACKOFF_S = 0.5


def _is_transient(e: LLMError) -> bool:
    """429 / 5xx / unknown-status errors (e.g. timeouts) are worth a same-provider
    retry. 4xx auth/validation errors (401/400/...) are terminal — retrying wastes
    time and won't change the outcome."""
    return e.status is None or e.status == 429 or 500 <= (e.status or 0) < 600


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
    db: AsyncSession | None = None,
    workspace_id: uuid.UUID | None = None,
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
        last_reason = ""
        for retry in range(_MAX_RETRIES + 1):
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
                if db is not None and workspace_id is not None:
                    # Lazy import avoids a providers↔llm_usage circular import.
                    from app.llm_usage.service import record_llm_usage

                    await record_llm_usage(
                        db, workspace_id=workspace_id, task_type=task_type.value, result=result
                    )
                return result
            except LLMError as e:
                last_reason = f"{type(e).__name__}({e.status or '-'}): {str(e)[:120]}"
                if _is_transient(e) and retry < _MAX_RETRIES:
                    log.info(
                        "llm.retry",
                        provider=provider_name,
                        attempt=retry + 1,
                        status=e.status,
                    )
                    await asyncio.sleep(_BACKOFF_S * (2**retry))
                    continue
                # Terminal error, or retries exhausted — fall through to next provider.
                duration_ms = int((time.perf_counter() - attempt_start) * 1000)
                log.warning(
                    "llm.fallback",
                    provider=provider_name,
                    reason=last_reason,
                    duration_ms=duration_ms,
                )
                attempts.append((provider_name, last_reason))
                break

    # All providers failed — surface the full chain in the raised error
    summary = "; ".join(f"{name}={reason}" for name, reason in attempts) or "empty chain"
    raise LLMError(f"all providers failed: {summary}", provider="factory")
