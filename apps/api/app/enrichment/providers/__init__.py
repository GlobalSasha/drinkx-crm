"""LLM provider abstractions — Sprint 1.3.A."""
from app.enrichment.providers.base import (
    CompletionResult,
    LLMAuthError,
    LLMError,
    LLMProvider,
    LLMRateLimited,
    LLMServerError,
    TaskType,
    is_flash_task,
)
from app.enrichment.providers.factory import complete_with_fallback, get_llm_provider

__all__ = [
    "LLMProvider",
    "CompletionResult",
    "LLMError",
    "LLMRateLimited",
    "LLMAuthError",
    "LLMServerError",
    "TaskType",
    "is_flash_task",
    "get_llm_provider",
    "complete_with_fallback",
]
