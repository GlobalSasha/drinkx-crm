"""llm_usage persistence + aggregation."""
from __future__ import annotations

import uuid
from decimal import Decimal

from app.llm_usage.models import LlmUsage


def insert_usage(
    db,
    *,
    workspace_id: uuid.UUID,
    task_type: str,
    provider: str,
    model: str | None,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: Decimal,
) -> None:
    """Stage a usage row on the caller's session — add() ONLY, no flush/commit.

    add() emits no SQL, so it cannot poison the caller's in-flight transaction
    and cannot commit the caller's other pending changes. The row persists when
    the caller commits its own transaction (every LLM call site commits right
    after the call). If the caller rolls back, the telemetry row is dropped too
    — acceptable for best-effort cost tracking.
    """
    db.add(
        LlmUsage(
            workspace_id=workspace_id,
            task_type=task_type,
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
        )
    )
