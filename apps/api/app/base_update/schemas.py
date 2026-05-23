"""AI-extraction Pydantic models. Permissive by design — these wrap raw
LLM output and MUST NOT raise on missing/garbage fields (PRD §7.2)."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

CANON_ROLES = {"economic_buyer", "champion", "technical_buyer", "operational_buyer"}
CANON_PRIORITY = {"A", "B", "C", "D"}


class ExtractedContact(BaseModel):
    name: str = ""
    title: str | None = None
    role_type: str | None = None
    email: str | None = None
    phone: str | None = None
    telegram: str | None = None
    linkedin: str | None = None
    source: str | None = None
    confidence: float = 0.0

    @field_validator("role_type", mode="before")
    @classmethod
    def _canon_role(cls, v):
        return v if v in CANON_ROLES else None


class ExtractedCompany(BaseModel):
    name: str = ""
    segment: str | None = None
    priority: str | None = None
    website: str | None = None
    inn: str | None = None
    city: str | None = None
    phone: str | None = None
    email: str | None = None

    @field_validator("priority", mode="before")
    @classmethod
    def _canon_priority(cls, v):
        s = str(v).strip().upper() if v is not None else None
        return s if s in CANON_PRIORITY else None


class ExtractedCard(BaseModel):
    company: ExtractedCompany = Field(default_factory=ExtractedCompany)
    contacts: list[ExtractedContact] = Field(default_factory=list)
    ai_brief: str = ""
    extraction_confidence: float = 0.0

    @field_validator("contacts", mode="before")
    @classmethod
    def _drop_non_dicts(cls, v):
        if not isinstance(v, list):
            return []
        return [x for x in v if isinstance(x, dict)]

    @field_validator("company", mode="before")
    @classmethod
    def _company_default(cls, v):
        return v if isinstance(v, dict) else {}

    @field_validator("extraction_confidence", mode="before")
    @classmethod
    def _clamp(cls, v):
        try:
            f = float(v)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, f))
