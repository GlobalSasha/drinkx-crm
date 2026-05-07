"""Application config — read from env via Pydantic Settings."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Core
    app_env: str = Field(default="development", description="development|staging|production")
    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:3000"]

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://drinkx:drinkx@localhost:5432/drinkx_crm",
        description="async SQLAlchemy URL",
    )

    # Redis (Celery broker + cache)
    redis_url: str = Field(default="redis://localhost:6379/0")

    # Supabase (Auth) — naming matches the modern Supabase dashboard:
    #   PUBLISHABLE_KEY = old "anon key" (safe in browser)
    #   SECRET_KEY      = old "service_role key" (server only)
    supabase_url: str = ""
    supabase_publishable_key: str = ""
    supabase_secret_key: str = ""
    supabase_jwt_secret: str = ""

    # AI providers — see CLAUDE.md and ADR-018
    # Primary: Xiaomi MiMo (OpenAI-compatible). Anthropic / Gemini / DeepSeek as fallbacks.
    mimo_api_key: str = ""
    mimo_base_url: str = "https://api.xiaomimimo.com/v1"
    mimo_model_pro: str = "mimo-v2-pro"      # high-value: Sales Coach, scoring, synthesis for fit≥8
    mimo_model_flash: str = "mimo-v2-flash"  # bulk/cheap: Research Agent, Daily Plan, pre-filter
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash-exp"
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    openai_api_key: str = ""                 # vision (GPT-4o) + emergency only
    brave_api_key: str = ""
    apify_token: str = ""

    # Default LLM backend + fallback chain (ADR-018)
    crm_ai_backend: str = "mimo"
    llm_fallback_chain: list[str] = ["mimo", "anthropic", "gemini", "deepseek"]

    # Sentry
    sentry_dsn: str = ""

    # AI cost guards
    ai_monthly_budget_usd: float = 200.0
    ai_max_parallel_jobs: int = 5
    ai_max_enrichments_per_lead_per_day: int = 1

    # SMTP — daily email digest (Sprint 1.5).
    # Stub mode is on while smtp_host is empty: rendered email is logged
    # to stdout instead of sent (mirrors ADR-014 stub-mode pattern).
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "DrinkX CRM <noreply@crm.drinkx.tech>"

    # Public-facing URLs — used to build OAuth redirect_uri and to send
    # the user back to the SPA after callback.
    api_base_url: str = "http://localhost:8000"
    frontend_base_url: str = "http://localhost:3000"

    # Google OAuth (Gmail Inbox sync — Sprint 2.0).
    # Reuses the same OAuth client as Supabase Google sign-in if it
    # already exists on the project. The Gmail readonly scope is
    # requested separately via /api/inbox/connect-gmail.
    google_client_id: str = ""
    google_client_secret: str = ""
    gmail_scopes: str = "https://www.googleapis.com/auth/gmail.readonly"
    gmail_history_months: int = 6
    gmail_sync_interval_minutes: int = 5
    gmail_max_body_chars: int = 10000


@lru_cache
def get_settings() -> Settings:
    return Settings()
