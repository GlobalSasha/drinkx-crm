"""Phone normalization to E.164 — Odoo `phone_validation` pattern (adapted).

Thin wrapper over `phonenumbers` (Google libphonenumber). The record keeps the
user's original `phone` untouched; this produces the canonical E.164 string
(`+79161234567`) stored alongside in `phone_e164` and used as a deduplication /
cross-channel match key.

Defaults to the RU region (the bulk of DrinkX leads), so inputs written without
a country prefix — `89161234567`, `8 (916) 123-45-67` — still resolve. Numbers
written with a leading `+` are parsed by their own country code.

Never raises: invalid or unparseable input yields ``None``, mirroring Odoo's
convention of only filling the sanitized column when the number is genuinely
valid.
"""
from __future__ import annotations

import phonenumbers

DEFAULT_REGION = "RU"


def to_e164(raw: str | None, region: str = DEFAULT_REGION) -> str | None:
    """Return the E.164 form of ``raw`` if it is a valid number, else ``None``."""
    if not raw or not raw.strip():
        return None
    try:
        parsed = phonenumbers.parse(raw, region)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(parsed):
        return None
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
