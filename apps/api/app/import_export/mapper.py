"""Header → field-key mapping suggestions + row renaming.

Stdlib only. Algorithm:
  1. Normalize each header: lowercase + strip + collapse non-alphanumerics
  2. For each (header, FieldDef), score against the field's key + label_ru
     + every alias. Best score across all candidates wins:
       - exact match           → 1.0
       - one starts-with the other → 0.8
       - either contains the other → 0.6
  3. A header gets a suggestion when its best score ≥ 0.6.
  4. Conflict resolution: if multiple headers point at the same field key,
     keep the highest-confidence header; lose the rest (they map to None).

Two source columns can never both map to the same target field — that's
how we keep the apply step deterministic.
"""
from __future__ import annotations

import re
from typing import Iterable

from app.import_export.field_map import LEAD_IMPORT_FIELDS, FieldDef


CONFIDENCE_THRESHOLD = 0.6
_NON_WORD = re.compile(r"[^a-zа-я0-9]+", re.IGNORECASE)


def _normalize(value: str) -> str:
    """Lowercase + collapse runs of punctuation/whitespace into single spaces.

    Keeps Cyrillic + Latin alphanumerics; drops everything else. So
    'E-mail' → 'e mail' and 'company_name' → 'company name'."""
    if not value:
        return ""
    lowered = value.lower().strip()
    return _NON_WORD.sub(" ", lowered).strip()


def _candidate_strings(fdef: FieldDef) -> Iterable[str]:
    """Every string a header could match against to claim this field."""
    yield _normalize(fdef.key)
    yield _normalize(fdef.label_ru)
    for a in fdef.aliases:
        yield _normalize(a)


def _score_against(header_norm: str, candidate: str) -> float:
    if not header_norm or not candidate:
        return 0.0
    if header_norm == candidate:
        return 1.0
    if header_norm.startswith(candidate) or candidate.startswith(header_norm):
        return 0.8
    if candidate in header_norm or header_norm in candidate:
        return 0.6
    return 0.0


def _best_field_for_header(
    header: str,
) -> tuple[str | None, float]:
    """Single-header search. Returns (field_key | None, confidence)."""
    h = _normalize(header)
    if not h:
        return None, 0.0
    best_key: str | None = None
    best_score = 0.0
    for fkey, fdef in LEAD_IMPORT_FIELDS.items():
        for cand in _candidate_strings(fdef):
            s = _score_against(h, cand)
            if s > best_score:
                best_score = s
                best_key = fkey
                if s == 1.0:
                    break
        if best_score == 1.0:
            break
    if best_score < CONFIDENCE_THRESHOLD:
        return None, 0.0
    return best_key, best_score


def suggest_mapping(headers: list[str]) -> dict[str, str | None]:
    """For each detected header → suggested LEAD_IMPORT_FIELDS key (or None).

    Conflicts (two headers want the same field) are resolved by confidence —
    the higher-scoring header keeps the mapping, the loser becomes None.
    Ties go to whichever header was scored first in the input order.
    """
    candidates: list[tuple[str, str | None, float]] = []
    for h in headers:
        key, score = _best_field_for_header(h)
        candidates.append((h, key, score))

    # Pick winner per field_key
    winner_per_key: dict[str, tuple[str, float]] = {}
    for h, key, score in candidates:
        if key is None:
            continue
        prev = winner_per_key.get(key)
        if prev is None or score > prev[1]:
            winner_per_key[key] = (h, score)

    winners_by_header: dict[str, str] = {
        h: k for k, (h, _) in winner_per_key.items()
    }

    return {h: winners_by_header.get(h) for h, _, _ in candidates}


def apply_mapping(
    rows: list[dict[str, str]],
    mapping: dict[str, str | None],
) -> list[dict[str, str]]:
    """Rename source columns to canonical keys. Unmapped source columns
    are dropped silently — the mapper already told the manager which
    source columns went unused at preview time."""
    keep = {src: dst for src, dst in mapping.items() if dst}
    out: list[dict[str, str]] = []
    for row in rows:
        renamed: dict[str, str] = {}
        for src, dst in keep.items():
            value = row.get(src, "")
            if value:
                renamed[dst] = value
        out.append(renamed)
    return out
