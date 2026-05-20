"""record_llm_usage — best-effort cost telemetry.

Called from the LLM chokepoint (complete_with_fallback) on success.
MUST NOT raise into the LLM path: a telemetry/DB failure logs a warning
and is swallowed so enrichment / Блейк / daily plan still get their result.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import structlog

from app.enrichment.providers.base import CompletionResult
from app.llm_usage.repositories import insert_usage

log = structlog.get_logger()

# Display order for providers in the admin counter (also drives zero-fill).
PROVIDER_ORDER = ["mimo", "anthropic", "gemini", "deepseek"]


async def record_llm_usage(
    db,
    *,
    workspace_id: uuid.UUID | None,
    task_type: str,
    result: CompletionResult,
) -> None:
    if db is None or workspace_id is None:
        log.warning("llm_usage.skip", provider=result.provider, task_type=task_type)
        return
    try:
        insert_usage(  # sync add-only; persists with the caller's transaction
            db,
            workspace_id=workspace_id,
            task_type=task_type,
            provider=result.provider,
            model=result.model,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            cost_usd=Decimal(str(result.cost_usd)),
        )
    except Exception as exc:  # noqa: BLE001 — telemetry must never break the LLM path
        log.warning("llm_usage.record_failed", error=str(exc), provider=result.provider)
