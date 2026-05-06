"""Research Agent output schema — fallback defaults everywhere (PRD §7.2)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DecisionMakerHint(BaseModel):
    name: str = ""
    title: str = ""
    role: Literal["economic_buyer", "champion", "technical_buyer", "operational_buyer", ""] = ""
    confidence: Literal["high", "medium", "low"] = "low"
    source: str = ""


class ResearchOutput(BaseModel):
    """Canonical AI enrichment output stored in lead.ai_data."""
    company_profile: str = Field(default="", description="2-3 sentence summary")
    network_scale: str = Field(default="")
    geography: str = Field(default="")
    formats: str = Field(default="")
    coffee_signals: str = Field(default="")
    growth_signals: list[str] = Field(default_factory=list)
    risk_signals: list[str] = Field(default_factory=list)
    decision_maker_hints: list[DecisionMakerHint] = Field(default_factory=list)
    fit_score: float = Field(default=0.0, ge=0.0, le=10.0, description="AI ICP match 0–10")
    next_steps: list[str] = Field(default_factory=list)
    urgency: Literal["high", "medium", "low", ""] = ""
    sources_used: list[str] = Field(default_factory=list)
    notes: str = ""
