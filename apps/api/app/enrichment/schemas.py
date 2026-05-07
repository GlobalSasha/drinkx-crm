"""Research Agent output schema — fallback defaults everywhere (PRD §7.2).

Strings (role, confidence, urgency) accept ANY value to avoid hard-failing the
whole pipeline when an LLM returns "закупки" instead of "economic_buyer". The
frontend normalizes/maps these for display. The synthesis prompt asks for the
canonical values, but we don't reject if it forgets.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Documented canonical values — used by the synthesis prompt and the frontend
# mapper. The schema itself stays permissive so a single bad enum doesn't
# nuke the whole research run into the notes-fallback.
ROLE_VALUES = ("economic_buyer", "champion", "technical_buyer", "operational_buyer", "")
CONFIDENCE_VALUES = ("high", "medium", "low")
URGENCY_VALUES = ("high", "medium", "low", "")


class DecisionMakerHint(BaseModel):
    name: str = ""
    title: str = ""
    role: str = ""          # canonical: ROLE_VALUES — but we accept any string
    confidence: str = "low"  # canonical: CONFIDENCE_VALUES
    source: str = ""


class ResearchOutput(BaseModel):
    """Canonical AI enrichment output stored in lead.ai_data."""
    company_profile: str = Field(default="", description="2-3 sentence business summary")
    network_scale: str = Field(default="")
    geography: str = Field(default="")
    # formats was Literal-style str earlier; LLMs frequently return a list so
    # we accept either and the frontend joins lists into a comma string.
    formats: list[str] | str = Field(default_factory=list)
    coffee_signals: list[str] | str = Field(default_factory=list)
    growth_signals: list[str] = Field(default_factory=list)
    risk_signals: list[str] = Field(default_factory=list)
    decision_maker_hints: list[DecisionMakerHint] = Field(default_factory=list)
    fit_score: float = Field(default=0.0, ge=0.0, le=10.0, description="AI ICP match 0–10")
    next_steps: list[str] = Field(default_factory=list)
    urgency: str = Field(default="")  # canonical: URGENCY_VALUES
    sources_used: list[str] = Field(default_factory=list)
    notes: str = ""
    score_rationale: str = Field(default="", description="2-3 предложения: почему именно такой fit_score (ссылки на конкретные сигналы из источников)")

    @field_validator("formats", "coffee_signals", mode="before")
    @classmethod
    def _coerce_to_list(cls, v):
        """LLMs sometimes return a single string for fields we'd like as lists.
        Accept both shapes; the frontend handles list-or-string."""
        return v
