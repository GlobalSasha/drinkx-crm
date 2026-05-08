"""Per-row validation rules.

Operates on rows where keys are already canonical (post-apply_mapping).
Stdlib only. Each rule returns a human-readable Russian message.

`segment` is intentionally NOT enum-validated — managers in different
workspaces use their own taxonomy (HoReCa / coffee_shops / Сеть кофеен / …)
and we'd reject perfectly good rows otherwise.
"""
from __future__ import annotations

import re
from typing import Any


_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_VALID_PRIORITIES = {"A", "B", "C", "D"}
_CURRENCY_STRIP_RE = re.compile(r"[\s ₽$€£¥]+")


def parse_deal_amount(raw: str) -> float | None:
    """Strip currency markers + whitespace, parse as float. Returns None
    if the string can't be coerced (caller flags as validation error)."""
    if not raw:
        return None
    cleaned = _CURRENCY_STRIP_RE.sub("", str(raw))
    cleaned = cleaned.replace(",", ".")  # RU decimal comma
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except (TypeError, ValueError):
        return None


def validate_row(row: dict[str, Any]) -> list[str]:
    """Return human-readable validation errors. Empty list = row is good."""
    errors: list[str] = []

    company = (row.get("company_name") or "").strip()
    if not company:
        errors.append("company_name: пусто")

    email = (row.get("email") or "").strip()
    if email and not _EMAIL_RE.match(email):
        errors.append(f"email: неверный формат ({email!r})")

    inn = (row.get("inn") or "").strip()
    if inn:
        digits = re.sub(r"\D", "", inn)
        if len(digits) not in (10, 12):
            errors.append(
                f"inn: ожидается 10 или 12 цифр, получено {len(digits)}"
            )

    deal_amount_raw = row.get("deal_amount")
    if deal_amount_raw:
        if parse_deal_amount(deal_amount_raw) is None:
            errors.append(f"deal_amount: не удалось распознать число ({deal_amount_raw!r})")

    priority_raw = (row.get("priority") or "").strip()
    if priority_raw:
        if priority_raw.upper() not in _VALID_PRIORITIES:
            errors.append(
                f"priority: ожидается A/B/C/D, получено {priority_raw!r}"
            )

    return errors
