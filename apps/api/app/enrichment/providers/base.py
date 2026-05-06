"""LLM Provider Protocol — common interface across MiMo, Anthropic, Gemini, DeepSeek."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class TaskType(str, Enum):
    """Drives the SKU choice within MiMo (per ADR-018) and routing decisions."""
    # Bulk / cheap → Flash
    research_synthesis = "research_synthesis"
    daily_plan = "daily_plan"
    prefilter = "prefilter"
    # High-value / heavy reasoning → Pro
    sales_coach = "sales_coach"
    scoring = "scoring"
    reenrichment_high_fit = "reenrichment_high_fit"


_FLASH_TASKS = {TaskType.research_synthesis, TaskType.daily_plan, TaskType.prefilter}


def is_flash_task(t: TaskType) -> bool:
    return t in _FLASH_TASKS


@dataclass(frozen=True, slots=True)
class CompletionResult:
    """Return value from any provider.complete() call."""
    text: str
    model: str
    provider: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0   # estimated; providers fill in from tokens × pricing


class LLMError(Exception):
    """Base for provider failures. Carries provider name + status code."""
    def __init__(self, message: str, *, provider: str, status: int | None = None):
        super().__init__(message)
        self.provider = provider
        self.status = status


class LLMRateLimited(LLMError):
    """Provider returned 429 / rate-limit. Should advance fallback chain."""


class LLMAuthError(LLMError):
    """Provider returned 401/403. Should advance fallback chain."""


class LLMServerError(LLMError):
    """Provider returned 5xx. Should advance fallback chain."""


class LLMProvider(Protocol):
    name: str

    async def complete(
        self,
        *,
        system: str,
        user: str,
        task_type: TaskType,
        max_tokens: int = 1024,
        temperature: float = 0.4,
        timeout_seconds: float = 30.0,
    ) -> CompletionResult: ...
