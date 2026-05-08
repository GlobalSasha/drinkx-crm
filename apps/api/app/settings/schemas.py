"""Settings domain Pydantic schemas — Sprint 2.4 G2.

Read-only views over already-existing config:
  - Gmail OAuth state per current user (from ChannelConnection rows
    written by the Sprint 2.0 OAuth flow).
  - SMTP config from app.config.Settings — surfaced for the admin
    Settings UI without exposing the password.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class GmailChannelOut(BaseModel):
    """Gmail connection state for the current user. Drives the
    «Подключить Gmail» / «Подключено» card in /settings → Каналы."""
    # Whether the SUPABASE_URL + GOOGLE_CLIENT_* env vars are
    # configured at all on the server. False → CTA goes through
    # but the API will reject with 503.
    configured: bool
    # Whether the current user has an active ChannelConnection row.
    # If `configured=True` and `connected=False`, the manager just
    # hasn't clicked Подключить yet.
    connected: bool
    # When was the last successful sync (NULL if never).
    last_sync_at: datetime | None = None


class SmtpConfigOut(BaseModel):
    """SMTP server config — read-only in v1. Editing is via env
    vars on the host, not via the UI (Sprint 2.4 NOT-ALLOWED:
    «DB-backed SMTP credentials»). Password is never returned."""
    configured: bool
    host: str
    port: int
    from_address: str
    # `user` is shown as a hint to the operator; password never is.
    user: str


class ChannelsStatusOut(BaseModel):
    gmail: GmailChannelOut
    smtp: SmtpConfigOut


# ---------------------------------------------------------------------------
# AI section — Sprint 2.4 G3
#
# Surfaces the workspace's per-day spend cap + preferred LLM provider.
# Stored in `workspace.settings_json["ai"]` (no migration — JSON column
# already exists since Sprint 1.1). The fallback chain in
# `app/enrichment/providers/factory.py` still reads env in v1; wiring the
# workspace override into the chain is a 2.4+ polish carryover so the UI
# value persists but doesn't yet alter live behavior. Documented in the
# AI card copy.
# ---------------------------------------------------------------------------

# Names match `app/enrichment/providers/factory.py:_REGISTRY`. Add new
# providers here in lock-step with the registry — anything not in this
# tuple is rejected at PATCH time.
AI_MODEL_CHOICES = ("deepseek", "anthropic", "gemini", "mimo")


class AISettingsOut(BaseModel):
    """GET /api/settings/ai response.

    `daily_budget_usd` and `primary_model` are the workspace overrides
    (or the env defaults if no override yet). `current_spend_usd_today`
    is read from the Redis budget counter so the gauge in the UI matches
    what the enrichment guard sees.
    """
    daily_budget_usd: float
    # Default if workspace hasn't picked a model yet — first item of
    # the env's llm_fallback_chain. Useful for the UI to render the
    # selector with a meaningful initial value.
    primary_model: str
    # Live spend today (UTC day boundary). 0.0 when Redis is unreachable
    # — see budget.get_daily_spend_usd's defensive fallback.
    current_spend_usd_today: float
    # Allowed values for the selector — keeps the frontend honest
    # without hardcoding the same list in two places.
    available_models: list[str]


class AISettingsUpdateIn(BaseModel):
    """PATCH /api/settings/ai body. Both fields optional — UI sends
    only the field it's changing. None means «leave as-is»."""
    daily_budget_usd: float | None = None
    primary_model: str | None = None
