"""Lead-scoring math — Lead Card v2 sprint.

Pure functions, no DB / no ORM imports — easy to unit-test and reuse
from the manual-edit endpoint, future bulk-recompute job, etc.

Formula (mirrors ADR-017): for each criterion in `scoring_criteria`
the manager picks a value 0..max_value. Contribution =
`value / max_value * weight`. Total = sum across criteria, rounded
to int. Weights are picked so sum == 100 by seed (8 criteria,
weights 20+15+15+15+10+10+10+5).

Priority letter is derived from total:

  total ≥ 80  →  A
  total ≥ 60  →  B
  total ≥ 40  →  C
  total <  40  →  D

`priority_label` is the human-readable Russian name the LeadCard
header pill renders instead of the raw letter.
"""
from __future__ import annotations

from dataclasses import dataclass


_PRIORITY_LABELS: dict[str, str] = {
    "A": "Стратегический",
    "B": "Перспективный",
    "C": "Низкий",
    "D": "Архив",
}


def priority_label(priority: str | None) -> str | None:
    """Map raw priority letter → Russian label. None passes through so
    callers can use this on un-scored leads without special-casing."""
    if not priority:
        return None
    return _PRIORITY_LABELS.get(priority)


def priority_from_score(total: int) -> str:
    """Threshold-based priority letter. 80/60/40 cutoffs."""
    if total >= 80:
        return "A"
    if total >= 60:
        return "B"
    if total >= 40:
        return "C"
    return "D"


@dataclass(frozen=True, slots=True)
class CriterionDef:
    """Minimal shape we need from a scoring_criteria row. The full
    ORM model lives in `app.auth.models.ScoringCriteria` — we accept
    plain dataclasses here so tests don't need a DB session."""

    key: str
    label: str
    weight: int
    max_value: int


def compute_total(
    criteria: list[CriterionDef],
    values: dict[str, int],
) -> int:
    """Sum `value / max_value * weight` across criteria. Missing keys
    contribute 0. Out-of-range values are clamped before contributing
    so a malformed JSON blob in the column can't blow the total past
    the configured max."""
    total = 0.0
    for c in criteria:
        if c.max_value <= 0:
            continue
        raw = values.get(c.key, 0)
        try:
            v = int(raw)
        except (TypeError, ValueError):
            continue
        v = max(0, min(c.max_value, v))
        total += (v / c.max_value) * c.weight
    return int(round(total))


def clean_values(
    criteria: list[CriterionDef],
    incoming: dict,
) -> dict[str, int]:
    """Whitelist + clamp an incoming patch. Keys outside the workspace
    config are dropped (no surprises in storage); values are clamped
    to 0..max_value. Non-int values are rejected (raises ValueError)
    so the caller can surface a 400."""
    allowed = {c.key: c for c in criteria}
    cleaned: dict[str, int] = {}
    for k, raw in (incoming or {}).items():
        if k not in allowed:
            continue
        try:
            v = int(raw)
        except (TypeError, ValueError):
            raise ValueError(f"score for {k!r} must be an integer")
        max_v = allowed[k].max_value
        if v < 0 or v > max_v:
            raise ValueError(
                f"score for {k!r} must be between 0 and {max_v}, got {v}"
            )
        cleaned[k] = v
    return cleaned
