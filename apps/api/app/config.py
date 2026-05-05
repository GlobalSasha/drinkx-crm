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

    # Supabase (Auth)
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_key: str = ""
    supabase_jwt_secret: str = ""

    # AI providers — see CLAUDE.md
    deepseek_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""
    brave_api_key: str = ""
    apify_token: str = ""

    # Default LLM backend
    crm_ai_backend: str = "deepseek"

    # Sentry
    sentry_dsn: str = ""

    # AI cost guards
    ai_monthly_budget_usd: float = 200.0
    ai_max_parallel_jobs: int = 5
    ai_max_enrichments_per_lead_per_day: int = 1


@lru_cache
def get_settings() -> Settings:
    return Settings()
