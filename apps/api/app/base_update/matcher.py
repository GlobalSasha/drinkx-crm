"""Pure classification helpers for matching extracted data against the base.

DB lookups happen in services.py; these functions take plain values/dicts
so they're unit-testable without a session.
"""
from __future__ import annotations

from app.base_update.constants import MIN_EXTRACTION_CONFIDENCE
from app.companies.utils import normalize_company_name


def _norm(v) -> str:
    """Lowercase, strip, return empty for None. NOT a name-collapse helper —
    use _collapse_ws on top for names."""
    return str(v).strip().lower() if v is not None else ""


def _collapse_ws(s: str) -> str:
    return " ".join(s.split())


def classify_field(*, base, incoming) -> str:
    """Return 'autofill' | 'noop' | 'conflict' for one field (#2)."""
    if incoming is None or _norm(incoming) == "":
        return "noop"
    if base is None or _norm(base) == "":
        return "autofill"
    if _norm(base) == _norm(incoming):
        return "noop"
    return "conflict"


def match_contact(base_contacts: list[dict], incoming_name: str) -> str | None:
    """Return the id of a base contact whose normalized name matches, else None (#3).

    An empty incoming name never matches (returning the empty-name base contact
    would be a false positive).
    """
    target = _collapse_ws(_norm(incoming_name))
    if not target:
        return None
    for ctc in base_contacts:
        if _collapse_ws(_norm(ctc.get("name"))) == target:
            return str(ctc.get("id"))
    return None


def is_low_confidence(extraction_confidence: float, *, company_name: str) -> bool:
    """#5 trigger: hold the record for review when the LLM is unsure or the
    company name is empty (we can't even match it to the base)."""
    if not (company_name or "").strip():
        return True
    return extraction_confidence < MIN_EXTRACTION_CONFIDENCE


def normalized_company_key(name: str) -> str:
    """Public alias so callers don't reach into companies.utils directly."""
    return normalize_company_name(name or "")
