"""llm_usage API schemas."""
from __future__ import annotations

from pydantic import BaseModel


class ProviderCostOut(BaseModel):
    provider: str
    cost_usd: float
    calls: int


class LlmCostsOut(BaseModel):
    period: str
    total_usd: float
    by_provider: list[ProviderCostOut]
