"""Bitrix24 deal/lead CSV export adapter.

Bitrix24 (a Russian-market CRM) exports leads as CSV with fixed Cyrillic
headers and — depending on the workspace locale and the export setting —
UTF-8 or CP1251 encoding. This adapter:

  - Detects the format via header heuristics (`is_bitrix24`)
  - Parses the file (`parse_bitrix24` — delegates to the generic CSV
    parser which already handles utf-8-sig and cp1251 fallback)
  - Translates Bitrix24 headers to our canonical Lead fields
    (`apply_bitrix24_mapping`); unknowns fall through to the generic
    fuzzy mapper

The router auto-promotes a CSV upload to Bitrix24 treatment when
`is_bitrix24(headers) is True` even without `?format=bitrix24` — the
manager just drops the file in and we figure it out.
"""
from __future__ import annotations

from app.import_export.mapper import suggest_mapping
from app.import_export.models import ImportJobFormat
from app.import_export.parsers import ParseResult, parse_file


# Bitrix24 header → our canonical Lead field key.
# Multiple synonyms map to the same field — Bitrix24 lets users rename
# columns at export time and different account types (deal vs lead) emit
# slightly different defaults.
BITRIX24_FIELD_MAP: dict[str, str] = {
    "Название":               "company_name",
    "Наименование":           "company_name",
    "Телефон":                "phone",
    "Рабочий телефон":        "phone",
    "EMAIL":                  "email",
    "E-mail":                 "email",
    "Сумма":                  "deal_amount",
    "Сумма сделки":           "deal_amount",
    "Сайт":                   "website",
    "ИНН":                    "inn",
    "Город":                  "city",
    "Город/населённый пункт": "city",
    "Комментарий":            "notes",
    "Примечание":             "notes",
    "Теги":                   "tags",
    "Метки":                  "tags",
    "Источник":               "source",
    "Источник лида":          "source",
}


# Headers we recognise as Bitrix24-native but deliberately don't import.
# Counted by `is_bitrix24` so a workspace exporting only system columns
# still gets recognised as Bitrix24 — the mapper just won't propose
# anything for these.
BITRIX24_IGNORED_FIELDS: frozenset[str] = frozenset({
    "ID",
    "Ответственный",
    "Стадия",
    "Дата создания",
    "Дата изменения",
    "Тип",
    "Компания",
    "Вероятность",
})


# ≥ this many Bitrix24-native headers required to flip auto-detect.
# Three is high enough to dodge a generic Russian CSV ("Название, Телефон,
# Email" by itself is not enough — `is_bitrix24` would tip True at three
# matches, which is fine because that's also exactly the shape Bitrix24
# emits for stripped-down exports).
BITRIX24_MIN_MATCHES: int = 3


def _known_headers() -> set[str]:
    return set(BITRIX24_FIELD_MAP.keys()) | BITRIX24_IGNORED_FIELDS


def is_bitrix24(headers: list[str]) -> bool:
    """True when at least `BITRIX24_MIN_MATCHES` of the given headers
    appear in either the mapped or the ignored set."""
    known = _known_headers()
    matches = sum(1 for h in headers if (h or "").strip() in known)
    return matches >= BITRIX24_MIN_MATCHES


def apply_bitrix24_mapping(headers: list[str]) -> dict[str, str | None]:
    """Same shape as `mapper.suggest_mapping`. Headers not in either
    Bitrix24 set fall through to the generic fuzzy mapper.

    Conflict-safe: if two source headers point at the same canonical
    field (Bitrix24 export rarely emits duplicates, but we defend), the
    first one wins and the rest become None. Mirrors the conflict
    resolution in `suggest_mapping` so the rest of the pipeline stays
    deterministic.
    """
    out: dict[str, str | None] = {}
    used_keys: set[str] = set()
    unknowns: list[str] = []

    # Step 1: explicit known headers (mapped or ignored)
    for h in headers:
        h_norm = (h or "").strip()
        if h_norm in BITRIX24_FIELD_MAP:
            target = BITRIX24_FIELD_MAP[h_norm]
            if target in used_keys:
                out[h] = None
            else:
                out[h] = target
                used_keys.add(target)
        elif h_norm in BITRIX24_IGNORED_FIELDS:
            out[h] = None
        else:
            unknowns.append(h)
            out[h] = None  # filled below if generic mapper finds a target

    # Step 2: generic fallback for the remainder, batched so the
    # generic mapper's own conflict resolution still applies among them.
    if unknowns:
        generic = suggest_mapping(unknowns)
        for h in unknowns:
            target = generic.get(h)
            if target and target not in used_keys:
                out[h] = target
                used_keys.add(target)
            else:
                out[h] = None

    return out


def parse_bitrix24(content: bytes) -> ParseResult:
    """Bitrix24 exports CSV under the hood — reuse the generic CSV parser
    which already handles utf-8-sig + cp1251 fallback and `;` / `,`
    delimiter detection."""
    return parse_file(content, "bitrix24.csv", ImportJobFormat.csv)


__all__ = [
    "BITRIX24_FIELD_MAP",
    "BITRIX24_IGNORED_FIELDS",
    "BITRIX24_MIN_MATCHES",
    "is_bitrix24",
    "apply_bitrix24_mapping",
    "parse_bitrix24",
]
