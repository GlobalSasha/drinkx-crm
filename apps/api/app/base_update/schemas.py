"""AI-extraction Pydantic models. Permissive by design — these wrap raw
LLM output and MUST NOT raise on missing/garbage fields (PRD §7.2)."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

CANON_ROLES = {"economic_buyer", "champion", "technical_buyer", "operational_buyer"}
CANON_PRIORITY = {"A", "B", "C", "D"}

_SCHEME_OK = ("http://", "https://")


def _strip_unsafe_url(v: object) -> str | None:
    """Coerce to a safe absolute http(s) URL or None — drops javascript:/data:/etc."""
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    low = s.lower()
    if any(low.startswith(p) for p in _SCHEME_OK):
        return s
    return None


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

    @model_validator(mode="before")
    @classmethod
    def _truncate_strings(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        caps = {
            "name": 200,
            "title": 200,
            "role_type": 40,
            "email": 254,
            "phone": 50,
            "telegram": 120,
            "linkedin": 500,
            "source": 120,
        }
        return {
            k: (v[: caps[k]] if k in caps and isinstance(v, str) else v)
            for k, v in data.items()
        }

    @field_validator("role_type", mode="before")
    @classmethod
    def _canon_role(cls, v: object) -> object:
        return v if v in CANON_ROLES else None

    @field_validator("linkedin", mode="before")
    @classmethod
    def _safe_linkedin(cls, v: object) -> str | None:
        return _strip_unsafe_url(v)

    @field_validator("telegram", mode="before")
    @classmethod
    def _safe_telegram(cls, v: object) -> str | None:
        # Accept http(s) t.me links; bare @handle stays as-is (text only, not used as href).
        # Unsafe schemes (javascript:, data:, etc.) are stripped to None.
        if v is None:
            return None
        s = str(v).strip()
        if not s:
            return None
        low = s.lower()
        if any(low.startswith(p) for p in _SCHEME_OK):
            return s
        # bare @handle or t.me/... without scheme: keep as text, not href
        return s


class ExtractedCompany(BaseModel):
    name: str = ""
    segment: str | None = None
    priority: str | None = None
    website: str | None = None
    inn: str | None = None
    city: str | None = None
    phone: str | None = None
    email: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _truncate_strings(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        caps = {
            "name": 255,
            "segment": 80,
            "priority": 2,
            "website": 500,
            "inn": 12,
            "city": 120,
            "phone": 50,
            "email": 254,
        }
        return {
            k: (v[: caps[k]] if k in caps and isinstance(v, str) else v)
            for k, v in data.items()
        }

    @field_validator("priority", mode="before")
    @classmethod
    def _canon_priority(cls, v: object) -> object:
        s = str(v).strip().upper() if v is not None else None
        return s if s in CANON_PRIORITY else None

    @field_validator("website", mode="before")
    @classmethod
    def _safe_website(cls, v: object) -> str | None:
        return _strip_unsafe_url(v)


class ExtractedCard(BaseModel):
    company: ExtractedCompany = Field(default_factory=ExtractedCompany)
    contacts: list[ExtractedContact] = Field(default_factory=list)
    ai_brief: str = ""
    extraction_confidence: float = 0.0

    @model_validator(mode="before")
    @classmethod
    def _truncate_strings(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        caps = {"ai_brief": 2000}
        return {
            k: (v[: caps[k]] if k in caps and isinstance(v, str) else v)
            for k, v in data.items()
        }

    @field_validator("contacts", mode="before")
    @classmethod
    def _drop_non_dicts(cls, v: object) -> object:
        if not isinstance(v, list):
            return []
        return [x for x in v if isinstance(x, dict)]

    @field_validator("company", mode="before")
    @classmethod
    def _company_default(cls, v: object) -> object:
        return v if isinstance(v, dict) else {}

    @field_validator("extraction_confidence", mode="before")
    @classmethod
    def _clamp(cls, v: object) -> float:
        try:
            f = float(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, f))
