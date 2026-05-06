"""Enrichment REST API DTOs."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class EnrichmentRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    lead_id: UUID
    user_id: UUID | None
    status: str
    provider: str | None
    model: str | None
    prompt_tokens: int
    completion_tokens: int
    cost_usd: Decimal
    duration_ms: int
    sources_used: list[str]
    error: str | None
    result_json: dict | None
    started_at: datetime
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class EnrichmentTriggerOut(BaseModel):
    """Returned by POST /leads/{id}/enrichment (202 Accepted)."""
    enrichment_run_id: UUID
    status: str  # "running"
