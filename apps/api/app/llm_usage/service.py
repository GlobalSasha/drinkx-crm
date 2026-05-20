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
from app.llm_usage.repositories import (
    Period,
    aggregate_by_provider,
    insert_usage,
    period_bounds,
)
from app.llm_usage.schemas import LlmCostsOut, ProviderCostOut

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
        log.debug("llm_usage.skip", provider=result.provider, task_type=task_type)
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


async def get_costs(db, *, workspace_id, period: Period) -> LlmCostsOut:
    start, end = period_bounds(period)
    rows = await aggregate_by_provider(db, workspace_id=workspace_id, start=start, end=end)
    found = {provider: (cost, calls) for provider, cost, calls in rows}
    by_provider = [
        ProviderCostOut(
            provider=p,
            cost_usd=round(found.get(p, (0.0, 0))[0], 6),
            calls=found.get(p, (0.0, 0))[1],
        )
        for p in PROVIDER_ORDER
    ]
    # Include any provider seen in data but not in PROVIDER_ORDER (defensive).
    for p, (cost, calls) in found.items():
        if p not in PROVIDER_ORDER:
            by_provider.append(ProviderCostOut(provider=p, cost_usd=round(cost, 6), calls=calls))
    total = round(sum(c.cost_usd for c in by_provider), 6)
    return LlmCostsOut(period=period, total_usd=total, by_provider=by_provider)
