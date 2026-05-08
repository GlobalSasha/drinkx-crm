"""Settings domain services — Sprint 2.4 G3.

Read + write the workspace-level AI section of `workspace.settings_json`.
The JSON column already exists (Sprint 1.1) so no migration; G3 just
plumbs a typed shape through the API.

The current spend number comes from the Redis counter that
`app.enrichment.budget` already maintains — keeps the UI gauge in
sync with what the enrichment guard sees, no second source of truth.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Workspace
from app.config import get_settings
from app.enrichment.budget import get_daily_spend_usd
from app.settings.schemas import AI_MODEL_CHOICES


# ---------------------------------------------------------------------------
# Custom exceptions — router maps to HTTP
# ---------------------------------------------------------------------------

class WorkspaceNotFound(Exception):
    """500 — current_user dependency would normally guarantee the
    workspace exists; raise on the off-chance it was deleted between
    the JWT verify and this query."""


class InvalidAIModel(Exception):
    """400 — primary_model must be one of AI_MODEL_CHOICES."""


class InvalidBudget(Exception):
    """400 — daily_budget_usd must be ≥ 0."""


# ---------------------------------------------------------------------------
# Helpers — shape of settings_json["ai"]
# ---------------------------------------------------------------------------

def _read_ai_section(workspace: Workspace) -> dict:
    """Pull the 'ai' subdict out of settings_json. Returns a fresh dict
    so the caller can mutate without aliasing the ORM-tracked column.
    SQLAlchemy notices replacement assignment on the column; in-place
    mutation of a JSON dict is NOT reliably detected on all backends."""
    raw = workspace.settings_json or {}
    return dict(raw.get("ai", {}))


def _env_defaults() -> tuple[float, str]:
    """Daily budget cap + preferred model derived from the env config —
    used when the workspace hasn't overridden the values yet."""
    s = get_settings()
    daily_cap = float(s.ai_monthly_budget_usd) / 30.0
    primary = s.llm_fallback_chain[0] if s.llm_fallback_chain else "deepseek"
    return daily_cap, primary


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

async def get_ai_settings(
    session: AsyncSession, *, workspace_id: uuid.UUID
) -> dict:
    """Resolve workspace overrides + env defaults into a single payload
    matching AISettingsOut. Returns a plain dict so the router can
    `model_validate` it.

    `current_spend_usd_today` comes from Redis (defensive — returns 0.0
    on connection error). The budget guard reads from the same key so
    the UI gauge can't drift from the enforcement number.
    """
    res = await session.execute(
        select(Workspace).where(Workspace.id == workspace_id)
    )
    workspace = res.scalar_one_or_none()
    if workspace is None:
        raise WorkspaceNotFound(str(workspace_id))

    ai = _read_ai_section(workspace)
    env_cap, env_primary = _env_defaults()

    daily_budget = float(ai.get("daily_budget_usd", env_cap))
    primary_model = str(ai.get("primary_model", env_primary))

    spend = await get_daily_spend_usd(workspace_id)

    return {
        "daily_budget_usd": daily_budget,
        "primary_model": primary_model,
        "current_spend_usd_today": float(spend),
        "available_models": list(AI_MODEL_CHOICES),
    }


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

async def update_ai_settings(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    daily_budget_usd: float | None = None,
    primary_model: str | None = None,
) -> dict:
    """Mutate `workspace.settings_json["ai"]` and return the resolved
    AISettingsOut payload. Caller commits.

    Validation rules:
      - daily_budget_usd must be ≥ 0 (a negative cap would silently
        disable budget enforcement — surface as 400 instead).
      - primary_model must be one of AI_MODEL_CHOICES — anything else
        would be a typo or a stale UI bundle.

    Both fields are optional; pass only what's changing. The full
    payload is returned so the UI doesn't need a follow-up GET.
    """
    if daily_budget_usd is not None and daily_budget_usd < 0:
        raise InvalidBudget(str(daily_budget_usd))
    if primary_model is not None and primary_model not in AI_MODEL_CHOICES:
        raise InvalidAIModel(primary_model)

    res = await session.execute(
        select(Workspace).where(Workspace.id == workspace_id)
    )
    workspace = res.scalar_one_or_none()
    if workspace is None:
        raise WorkspaceNotFound(str(workspace_id))

    settings_json = dict(workspace.settings_json or {})
    ai = dict(settings_json.get("ai", {}))

    if daily_budget_usd is not None:
        ai["daily_budget_usd"] = float(daily_budget_usd)
    if primary_model is not None:
        ai["primary_model"] = primary_model

    settings_json["ai"] = ai
    # Reassign the whole dict — SQLAlchemy's mutation tracking on JSON
    # columns is opt-in; replacement is the safe default (matches how
    # the rest of the codebase writes settings_json).
    workspace.settings_json = settings_json
    await session.flush()

    env_cap, env_primary = _env_defaults()
    spend = await get_daily_spend_usd(workspace_id)

    return {
        "daily_budget_usd": float(ai.get("daily_budget_usd", env_cap)),
        "primary_model": str(ai.get("primary_model", env_primary)),
        "current_spend_usd_today": float(spend),
        "available_models": list(AI_MODEL_CHOICES),
    }
