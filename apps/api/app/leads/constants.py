"""Sprint 3.5 — canonical segment vocabulary + city normalization.

ADR-023: `leads.segment` and `companies.primary_segment` are VARCHAR(50) at
the DB level (no ALTER TYPE) but the application enforces an 8-value list.
Adding a new segment is a code change + data backfill, not a DB migration.

Keys preserved from the v0.5/v0.6 prototype import (`scripts/build_data.py`,
`scripts/build_foodmarkets_data.py`) so existing 216 production rows do
not require value rewrites. One legacy key is renamed in migration 0027:
`coffee_equipment_distributors` → `distributor`.
"""
from __future__ import annotations

import re

SEGMENT_CHOICES: list[tuple[str, str]] = [
    ("food_retail",     "Продуктовый ритейл"),
    ("non_food_retail", "Непродуктовый ритейл"),
    ("coffee_shops",    "Кофейни / Кафе / Рестораны"),
    ("qsr_fast_food",   "QSR / Fast Food"),
    ("gas_stations",    "АЗС"),
    ("office",          "Офисы"),
    ("hotel",           "Отели"),
    ("distributor",     "Дистрибьюторы"),
]

SEGMENT_KEYS: list[str] = [key for key, _ in SEGMENT_CHOICES]
SEGMENT_LABELS: dict[str, str] = dict(SEGMENT_CHOICES)


_CITY_PREFIX_RE = re.compile(r"^г\.?\s+|^г\.\s*", re.IGNORECASE)


def normalize_city(city: str | None) -> str | None:
    """Strip "г.", "г " prefix, trim whitespace, capitalize first letter.

    Returns None for empty / whitespace-only input so callers can store NULL
    instead of an empty string.
    """
    if not city:
        return None
    s = city.strip()
    if not s:
        return None
    s = _CITY_PREFIX_RE.sub("", s).strip()
    if not s:
        return None
    return s[0].upper() + s[1:]
